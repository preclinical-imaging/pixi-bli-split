import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Union

import requests
from requests.auth import HTTPBasicAuth

from Bli import Bli

logging.basicConfig(stream=sys.stdout,
                    filemode="w",
                    format="%(levelname)s %(asctime)s - %(message)s",
                    level=logging.INFO)

logger = logging.getLogger()


def run(scans_directory: Union[Path, str], output_directory: Union[Path, str],
        xnat_username: str, xnat_password: str, xnat_host: str, project: str, experiment: str,
        animal_numbers: list, bboxes: list):
    """
    Splits each multi-subject BLI scan (one scan per directory) into single-subject scans then sends the output to XNAT.
    """

    # For testing locally running within a Docker container
    if xnat_host == 'http://localhost':
        xnat_host = 'http://host.docker.internal'

    # Make output directories
    output_directory = Path(output_directory)

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    if not os.path.exists(output_directory / 'qc'):
        os.makedirs(output_directory / 'qc')

    # Expecting XNAT's ../SCANS directory. Each scan should be a subdirectory
    scans_directory = Path(scans_directory)
    scan_directories = [x for x in scans_directory.iterdir() if x.is_dir()]

    # For each BLI scan directory split and save each scan to the output directory.
    # Output directory structure output_dir/animal_number / scan_directory_name
    for scan_directory in scan_directories:

        bli = Bli.from_path(scan_directory)
        logger.info(f'BLI scan created for directory: {scan_directory}')

        split_blis = []

        if bboxes:
            logger.info("Manually splitting BLI scan in directory")

            if not animal_numbers:
                # Try to get animal numbers from BLI session if not provided
                if bli.animal_numbers:
                    animal_numbers = bli.animal_numbers
                else:
                    animal_numbers = ['Unknown', 'Unknown', 'Unknown', 'Unknown', 'Unknown']

            logger.debug(f'Splitting with animal numbers: {animal_numbers}')
            logger.debug(f'Splitting with boundary boxes: {bboxes}')

            for animal_number, bbox in zip(animal_numbers, bboxes):
                # Skip Empty and X
                if not animal_number.lower() == 'empty' and not animal_number.lower() == 'x':
                    split_blis.append(bli.crop(animal_number, tuple(bbox)))

        else:
            logger.info("Automatic threshold splitting of BLI scan")
            split_blis, qc_image = bli.threshold_split()
            qc_image.save(output_directory / 'qc' / f'qc_image_{scan_directory.name}.tif')

        for split_bli in split_blis:
            animal_number = split_bli.animal_numbers[0]

            # Save the split BLI session
            split_output_directory = output_directory / animal_number / scan_directory.name
            split_bli.save(split_output_directory)

    # Zip each subject output directory and send it to XNAT, skipping the qc directory
    subject_directories = [x for x in output_directory.iterdir() if x.is_dir() and x.name != 'qc']
    for subject_directory in subject_directories:
        # Zip the split BLI session
        zip_file = output_directory / f'{subject_directory.name}.zip'
        zip_dir(subject_directory, zip_file)

        send_to_xnat(xnat_username=xnat_username, xnat_password=xnat_password, xnat_host=xnat_host,
                     project=project, subject=subject_directory.name, experiment=experiment,
                     zip_file=zip_file)


def send_to_xnat(xnat_username: str, xnat_password: str, xnat_host: str,
                 project: str, subject: str, experiment: str,
                 zip_file: Union[Path, str]):

    experiment = experiment + "_split_" + subject

    url = f'{xnat_host}/data/services/import'
    params = {
        'import-handler': 'BLI',
        'overwrite': 'append',
        'PROJECT_ID': project,
        'SUBJECT_ID': subject,
        'EXPT_LABEL': experiment
    }

    logger.info(f'Uploading {zip_file} for project {project}, subject {subject}, experiment {experiment} to {url}')

    r = requests.post(url,
                      auth=HTTPBasicAuth(xnat_username, xnat_password),
                      params=params,
                      files={'file': open(zip_file, 'rb')})

    if r.ok:
        logger.info('Upload successful')
    else:
        logger.error(f'Upload failed: {r.text}')
        raise Exception(f'Upload failed for project {project}, subject {subject}, experiment {experiment}')


def zip_dir(directory: Union[Path, str], filename: Union[Path, str]):
    """Zip the provided directory"""

    directory = Path(directory)

    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(directory):
            zip_file.write(root, os.path.relpath(root, os.path.join(directory, '..')))
            for file in files:
                zip_file.write(os.path.join(root, file),
                               os.path.relpath(os.path.join(root, file),
                                               os.path.join(directory, '..')))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('scans_directory')
    parser.add_argument('-x', '--xnat_host', type=str, default=None, required=True, help="XNAT Host")
    parser.add_argument('-u', '--xnat_username',  type=str, default=None, required=True, help="XNAT Username")
    parser.add_argument('-p', '--xnat_password',  type=str, default=None, required=True, help="XNAT Password")
    parser.add_argument('--project',       type=str, default=None, required=True, help="XNAT Project ID")
    parser.add_argument('--experiment',    type=str, default=None, required=True, help="XNAT Experiment Label")
    parser.add_argument('--output_directory', type=str, default=None, required=True, help="Output directory")

    parser.add_argument('-a', '--animal_numbers', type=str, default=None, nargs=5, required=False,
                        help="For manual splitting, provide each animal number left to right.")
    parser.add_argument('-b', '--bbox', type=int, default=None, nargs=4, required=False, dest="bboxes", action='append',
                        help="For manual splitting, supply the boundary box for each animal in photograph.tif from left"
                             " to right. Provide this argument 5 times, one for each animal.")

    kwargs = vars(parser.parse_args())

    run(**kwargs)

