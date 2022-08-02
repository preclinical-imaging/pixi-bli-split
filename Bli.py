import copy
import json
import logging
import os
from math import ceil, floor
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageDraw
from skimage import filters
from skimage import measure

logger = logging.getLogger(__name__)


# Source https://datagy.io/python-round-to-multiple/
def round_to_multiple(number, multiple, direction='nearest'):
    if direction == 'nearest':
        return multiple * round(number / multiple)
    elif direction == 'up':
        return multiple * ceil(number / multiple)
    elif direction == 'down':
        return multiple * floor(number / multiple)
    else:
        return multiple * round(number / multiple)


class Bli:
    """
    Class to represent a Bioluminescence Imaging scan obtained from a PerkinElmer IVIS System

    Each BLI scan directory is expected to contain the following:
        AnalyzedClickInfo.json
        background.tif
        luminescent.tif
        photograph.tif
        readbias.tif

    AnalyzedClickInfo.txt file is converted to AnalyzedClickInfo.json during PIXI's import process.

    photograph.tif is four times larger than the other images. The crop applied to photograph.tif is scaled down by a
    factor of four.
    """

    def __init__(self, path: Union[Path, str] = None,
                 photograph_tif: Image = None,
                 luminescent_tif: Image = None,
                 background_tif: Image = None,
                 readbias_tif: Image = None,
                 analyzedclickinfo: dict = None):
        """
        Main method for constructing BLI object.

        Option 1 - construct from path.
        Option 2 - construct from PIL Images and analyzedclickinfo dictionary

        See factory methods below.
        """

        if path:
            self.path = Path(path)
            self.photograph_tif, self.luminescent_tif, self.background_tif, self.readbias_tif = self.load_images(self.path)
            self.analyzedclickinfo = self.load_analyzed_click_info(self.path)
        elif photograph_tif and luminescent_tif and background_tif and readbias_tif:
            self.path = None
            self.photograph_tif = photograph_tif
            self.luminescent_tif = luminescent_tif
            self.background_tif = background_tif
            self.readbias_tif = readbias_tif
            self.analyzedclickinfo = analyzedclickinfo

        self.animal_numbers = self.__get_animal_numbers()

    @classmethod
    def from_path(cls, path: Union[Path, str]):
        """
        Construct Bli scan from the supplied path.

        Parameters
        ----------
        path : Union[Path, str]
            Path to a Bli scan

        Returns
        -------
        Bli
            A Bli scan from the provided path.
        """
        return cls(path=path)

    @classmethod
    def from_images(cls, photograph_tif: Image, luminescent_tif: Image, background_tif: Image, readbias_tif: Image,
                    analyzedclickinfo: dict):
        """
        Construct Bli scan from the supplied PIL Images and analyzedclickinfo dictionary.

        Parameters
        ----------
        photograph_tif : Image
            PIL Image for photograph.tif
        luminescent_tif : Image
            PIL Image for luminescent.tif
        background_tif : Image
            PIL Image for background.tif
        readbias_tif : Image
            PIL Image for readbias.tif
        analyzedclickinfo : dict
            AnalyzedClickInfo.txt converted to dictionary format.

        Returns
        -------
        Bli
            A Bli scan from the provided images and analyzedclickinfo.
        """
        return cls(photograph_tif=photograph_tif,
                   luminescent_tif=luminescent_tif,
                   background_tif=background_tif,
                   readbias_tif=readbias_tif,
                   analyzedclickinfo=analyzedclickinfo)

    @staticmethod
    def load_images(path: Union[Path, str]):
        """
        Load photograph.tif, luminescent.tif, background.tif, and readbias.tif from the provided directory.

        Parameters
        ----------
        path : Union[Path, str]
            Path to a directory containing photograph.tif, luminescent.tif, background.tif, and readbias.tif

        Returns
        -------
        tuple[Image, Image, Image, Image]
            4-tuple of photograph_tif, luminescent_tif, background_tif, readbias_tif opened as a PIL Image

        """
        path = Path(path)

        photograph_tif = None
        luminescent_tif = None
        background_tif = None
        readbias_tif = None

        for subpath in path.rglob('*'):
            if subpath.is_file():
                filename = subpath.name.lower()

                match filename:
                    case 'photograph.tif':
                        photograph_tif = Image.open(str(subpath))
                        logger.debug(f'photograph.tif read: {subpath}')
                    case 'luminescent.tif':
                        luminescent_tif = Image.open(str(subpath))
                        logger.debug(f'luminescent.tif read: {subpath}')
                    case 'background.tif':
                        background_tif = Image.open(str(subpath))
                        logger.debug(f'background.tif read: {subpath}')
                    case 'readbias.tif':
                        readbias_tif = Image.open(subpath)
                        logger.debug(f'readbias.tif read: {subpath}')

        return photograph_tif, luminescent_tif, background_tif, readbias_tif

    @staticmethod
    def load_analyzed_click_info(path: Union[Path, str]):
        """
        Load analyzedclickinfo.json into a dictionary.

        TODO Parse analyzedclickinfo.txt.

        Parameters
        ----------
        path : Union[Path, str]
            Path to a directory containing analyzedclickinfo.json

        Returns
        -------
        dict
            path/analyzedclickinfo.json loaded into a dictionary
        """
        path = Path(path)

        analyzedclickinfo_json = None
        analyzedclickinfo_txt = None

        for subpath in path.rglob('*'):
            if subpath.is_file():
                filename = subpath.name.lower()

                match filename:
                    case 'analyzedclickinfo.txt':
                        logger.debug(f'TODO analyzedclickinfo.txt found: {subpath}')  # TODO
                    case 'analyzedclickinfo.json':
                        with open(subpath, "r") as file:
                            analyzedclickinfo_json = json.load(file)
                            logger.debug(f'analyzedclickinfo.json read: {subpath}')

        return analyzedclickinfo_json

    def crop(self, animal_number: str, bounding_box: tuple[int, int, int, int]):
        """
        Crops each image in the BLI scan and returns a new BLI scan.

        Parameters
        ----------
        animal_number : str
            The animal number associated with the area being cropped. The new BLI scan will use this animal number in
            place of the animal number from the original BLI scan.
        bounding_box : tuple[int, int, int, int]
            A 4-tuple defining the left, upper, right, and lower pixel coordinate.

        Returns
        -------
        Bli
           Returns a BLI scan with each image cropped to the provided area.
        """

        # a 4-tuple defining the left, upper, right, and lower pixel coordinate.
        logging.debug(f'Splitting photograph.tif with bounding box: {bounding_box}')
        split_photograph_tif = self.photograph_tif.crop(bounding_box)

        # Photograph TIF is 4 times larger than the other TIF images. Reduce the bound box.
        bounding_box = tuple(int(i / 4) for i in bounding_box)
        logging.debug(f'Splitting luminescent.tif, background.tif, and readbias.tif with bounding box: {bounding_box}')

        split_luminescent_tif = self.luminescent_tif.crop(bounding_box)
        split_background_tif = self.background_tif.crop(bounding_box)
        split_readbias_tif = self.readbias_tif.crop(bounding_box)

        # Update the AnalyzedClickInfo with the provided animal number
        split_analyzedclickinfo = None
        if self.analyzedclickinfo:
            split_analyzedclickinfo = copy.deepcopy(self.analyzedclickinfo)
            split_analyzedclickinfo['userLabelNameSet']['animalNumber'] = animal_number

        return Bli.from_images(photograph_tif=split_photograph_tif,
                               luminescent_tif=split_luminescent_tif,
                               background_tif=split_background_tif,
                               readbias_tif=split_readbias_tif,
                               analyzedclickinfo=split_analyzedclickinfo)

    def threshold_split(self, return_qc_image=True):
        """
        Use Li thresholding to segment the animals from the Bli scan.

        Parameters
        ----------
        return_qc_image : bool
            Generate and return a quality control snapshot showing how the animals were segmented.

        Returns
        -------
        list[Bli]
            A list containing a Bli scan for each animal segmented from the original Bli scan.
        """
        num_animals = len(self.animal_numbers)

        # Threshold the photograph image
        thresh = filters.threshold_li(np.asarray(self.photograph_tif))
        blobs = self.photograph_tif > thresh
        (blob_labels, num) = measure.label(blobs, return_num=True, background=0, connectivity=1)
        region_props = measure.regionprops(blob_labels)

        # Get the largest regions, these should correspond to animals
        region_props.sort(key=lambda p: p.area, reverse=True)
        region_props = region_props[:num_animals]

        # Sort the regions from left most to right most
        region_props.sort(key=lambda p: p.bbox[1])

        # Setup QC image
        qc_image = None
        qc_image_draw = None
        colors = ['#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7']

        if return_qc_image:
            qc_image = Image.fromarray(blobs).convert('RGB')
            qc_image_draw = ImageDraw.Draw(qc_image)

        # Split into n BLI sessions
        split_blis = []
        for region_prop, animal_number, color in zip(region_props, self.animal_numbers, colors):
            # Scale the bounding box up to a multiple of 4
            bbox = region_prop.bbox
            bbox = tuple([round_to_multiple(i, 4, 'up') for i in bbox])

            # scikit bbox    -> (min_row, min_col, max_row, max_col)
            # PIL Image bbox -> (min_col, min_row, max_col, max_row)
            min_row, min_col, max_row, max_col = bbox
            bbox = (min_col, min_row, max_col, max_row)
            split_blis.append(self.crop(animal_number, bbox))

            if qc_image and qc_image_draw:
                qc_image_draw.rectangle((min_col, min_row, max_col, max_row), outline=color, width=2)

        if return_qc_image:
            return split_blis, qc_image
        else:
            return split_blis

    def __get_animal_numbers(self):
        """Parse the animal number string from analyzedclickinfo['userLabelNameSet']['animalNumber']"""
        if self.analyzedclickinfo:
            return list(map(lambda x: x.strip(), self.analyzedclickinfo['userLabelNameSet']['animalNumber'].split(',')))
        else:
            return None

    def save(self, path: Union[Path, str]):
        """
        Save the Bli scan to the provided path

        Parameters
        ----------
        path : Union[Path, str]
            Path to save photograph.tif, luminescent.tif, background.tif, and readbias.tif and analyzedclickinfo.json
            to.
        """
        path = Path(path)

        if not os.path.exists(path):
            os.makedirs(path)

        self.photograph_tif.save(path / 'photograph.tif')
        self.luminescent_tif.save(path / 'luminescent.tif')
        self.background_tif.save(path / 'background.tif')
        self.readbias_tif.save(path / 'readbias.tif')

        if self.analyzedclickinfo:
            with open(path / 'AnalyzedClickInfo.json', 'x') as file:
                json.dump(self.analyzedclickinfo, file, indent=4)

    def __del__(self):
        """Close photograph.tif, luminescent.tif, background.tif, and readbias.tif when an instance is deleted."""
        self.photograph_tif.close()
        self.luminescent_tif.close()
        self.background_tif.close()
        self.readbias_tif.close()

