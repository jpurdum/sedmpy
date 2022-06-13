#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Wed Feb 26 2020

@author: neill
"""
import subprocess
from astropy.io import fits as pf

try:
    import fitsutils
except ImportError:
    import drprc.fitsutils as fitsutils
import os
import glob
import argparse
import json
import sedmpy_version

try:
    configfile = os.environ["SEDMCONFIG"]
except KeyError:
    configfile = os.path.join(sedmpy_version.CONFIG_DIR, 'sedmconfig.json')
with open(configfile) as config_file:
    sedm_cfg = json.load(config_file)

# Default paths
_photpath = sedm_cfg['paths']['photpath']

    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
    
    Creates an animated gif of guider images used for the science image
    in the folder specified as a parameter.
        
    """, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-i', '--imfile', type=str, dest="imfile",
                        help='IFU image that requires a finder',
                        default=None)
    
    args = parser.parse_args()

    imfile = args.imfile

    if imfile:
        timestamp = imfile.split('/')[-2]
        rcdir = os.path.join(_photpath, timestamp)
        reduxdir = '/'.join(imfile.split('/')[0:-1])
        objnam = fitsutils.get_par(imfile, "OBJECT").split()[0]
        if 'STD' in objnam:
            objnam = objnam.split('STD-')[-1].split()[0]

        os.chdir(reduxdir)

        print("Making guider movie for object: %s" % objnam)
        print("Changed to directory where the reduced data is: %s" % reduxdir)
        print("Getting guider images from directory: %s" % rcdir)

        # We gather all RC images to locate the Guider ones.
        files = glob.glob(os.path.join(rcdir, "rc*[0-9].fit*"))
        files.sort()
        filesguide = []
        pngdir = os.path.join(rcdir, 'pngraw/guider')

        for f in files:
            try:
                ff = pf.open(f)
            except OSError:
                print("WARNING - corrupt fits file: %s" % f)
                continue
            if "IMGTYPE" in ff[0].header:
                imgtype = ff[0].header["IMGTYPE"]
            else:
                imgtype = ''
            if "OBJECT" in ff[0].header:
                obj = ff[0].header["OBJECT"]
            else:
                obj = ''

            ff.close()

            if 'GUIDE' in imgtype.upper() and objnam in obj:
                pngf = os.path.basename(f).split('.fits')[0] + '_all.png'
                filesguide.append(os.path.join(pngdir, pngf))

        n_guide = len(filesguide)
        print("Found %d files used for quiding %s" % (n_guide, objnam))
        outmov = os.path.join(
            pngdir,
            os.path.basename(imfile).split('.fits')[0] + '_' + objnam +
            '_guide_movie.gif')
        cmd = 'convert -delay 20 ' + ' '.join(filesguide) + ' -loop 1 ' + outmov
        print(cmd)
        subprocess.run(cmd, shell=True)
    else:
        print("Please specify an input IFU image that was guided.")
