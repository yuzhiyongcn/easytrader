# -*- coding: utf-8 -*-
import urllib3

from easytrader import exceptions
from easytrader.api import use, follower
from easytrader.log import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

__version__ = "1.0.0"
__author__ = "piginzoo"
