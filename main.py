#!/usr/bin/env python3
"""
Module Docstring
"""

__author__ = "Andreas Ehrlund"
__version__ = "0.1.0"
__license__ = "MIT"

from pymkm import PyMKM


def main():
    """ Main entry point of the app """
    print(">>> Welcome to a pymkm test app.")

    api = PyMKM()
    try:
        #response = api.get_account()
        #print(response)
        #response = api.set_display_language(2)
        #print(response)
        response = api.set_vacation_status(True)
        print(response)
    except ValueError as err:
        print(err)


if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()