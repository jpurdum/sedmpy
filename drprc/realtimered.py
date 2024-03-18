# -*- coding: utf-8 -*-
"""
Created on Thu Mar  3 19:23:29 2016

@author: nadiablago
"""
try:
    import rcred
except ImportError:
    import drprc.rcred as rcred
import subprocess
import glob
import os
import time
import argparse
try:
    import fitsutils
except ImportError:
    import drprc.fitsutils as fitsutils
try:
    from target_mag import get_target_mag
except ImportError:
    from drprc.target_mag import get_target_mag
try:
    from fritz_status_update import update_fritz_status
except ImportError:
    from fritz.fritz_status_update import update_fritz_status

try:
    from pysedmpush import slack
except ImportError:
    slack = None
    print("you need to install pysedmpush to be able to push on slack")
from datetime import datetime
import logging
from astropy.io import fits
from astropy.time import Time
import astroplan
from matplotlib import pylab as plt
import numpy as np
from scipy.stats import sigmaclip
import sedmpy_version
import json

# Get pipeline configuration
# Find config file: default is sedmpy/config/sedmconfig.json
try:
    configfile = os.environ["SEDMCONFIG"]
except KeyError:
    configfile = os.path.join(sedmpy_version.CONFIG_DIR, 'sedmconfig.json')
with open(configfile) as config_file:
    sedm_cfg = json.load(config_file)

_logpath = sedm_cfg['paths']['logpath']
_photpath = sedm_cfg['paths']['photpath']

SLACK_CHANNEL = "pysedm-report"

plt.switch_backend('Agg')

# Log into a file
log_format = '%(asctime)-15s %(levelname)s [%(name)s] %(message)s'
root_dir = _logpath
timestamp = datetime.isoformat(datetime.utcnow())
timestamp = timestamp.split("T")[0]
logging.basicConfig(format=log_format,
                    filename=os.path.join(root_dir,
                                          "rcred_{0}.log".format(timestamp)),
                    level=logging.INFO)
logger = logging.getLogger('realtimered')


def gzip_fits_files(curdir):
    """gzip all the fits files in current directory"""
    # top level
    utdstr = curdir.split('/')[-1]
    flist = glob.glob(os.path.join(curdir, '*.fits'))
    ntgzip = 0
    for fl in flist:
        # Skip cal files
        if 'Bias' in fl or 'Flat' in fl:
            continue
        if os.path.isfile(fl) and not os.path.islink(fl):
            subprocess.run(["gzip", fl])
            ntgzip += 1
    # reduced level
    flist = glob.glob(os.path.join(curdir, 'reduced', '*.fits'))
    nrgzip = 0
    for fl in flist:
        if os.path.isfile(fl) and not os.path.islink(fl):
            subprocess.run(["gzip", fl])
            nrgzip += 1
    # append dir to backup file
    back_file = sedm_cfg['backup']['phot_backup_file']
    try:
        with open(back_file, 'w') as bf:
            bf.writelines(utdstr + "\n")
        print("%s written to %s, ready for rsync" % (utdstr, back_file))
    except OSError:
        print("Cannot open backup file for update: %s" % back_file)

    return ntgzip, nrgzip


def plot_raw_image(image, verbose=False, ut_id=None):
    """
    Plots the reduced image into the png folder.

    """
    image = os.path.abspath(image)

    try:
        utdate = int(os.path.basename(image)[2:10])
    except ValueError:
        utdate = int(image.split('/')[-2])

    try:
        ff = fits.open(image)[0]
        d = ff.data.astype(np.float64)
        h = ff.header
    except OSError:
        logger.error("FATAL! Could not open image %s." % image)
        return
    except TypeError:
        logger.error("FATAL! Buffer size error for image %s." % image)
        return

    imtype = h.get('IMGTYPE', 'None')
    exptime = h.get('EXPTIME', 0)
    name = h.get('OBJECT', 'None')
    filt = h.get('FILTER', 'NA')
    focpos = h.get('FOCPOS', 0.)

    # Sub-dir
    if utdate < 20181210:
        if 'dome' in imtype.lower() or 'bias' in imtype.lower():
            subdir = imtype.lower().strip()
        else:
            obtype = h.get('OBJTYPE', 'None')
            if 'science' in imtype.lower():
                if 'calibration' in obtype.lower():
                    obname = h.get('OBJNAME')
                    if 'twilight' in obname.lower() or \
                            'twlight' in obname.lower():
                        subdir = 'twilight'
                    elif 'focus' in obname.lower() or 'focus' in name.lower():
                        subdir = 'focus'
                    else:
                        subdir = 'test'
                elif 'Twilight' in obtype:
                    subdir = 'twilight'
                elif 'TRANSIENT' in obtype:
                    subdir = 'science'
                elif 'SHOT' in obtype:
                    subdir = 'science'
                else:
                    subdir = obtype.lower().strip()
                    if len(subdir) <= 0:
                        if 'finding' in name.lower():
                            subdir = 'acquisition'
                        else:
                            subdir = 'guider'
            elif 'Twilight' in imtype:
                subdir = 'twilight'
            elif 'lamp' in imtype:
                if 'twlight' in name.lower() or 'twilight' in name.lower():
                    subdir = 'twilight'
                else:
                    subdir = obtype.lower().strip()
                    if len(subdir) <= 0:
                        subdir = 'test'
            elif 'focus' in name.lower():
                subdir = 'focus'
            elif 'standard' in imtype.lower():
                subdir = 'science'
            else:
                subdir = obtype.lower().strip()
                if len(subdir) <= 0:
                    subdir = 'test'
    else:
        subdir = imtype.lower().strip()
    
    # Change to image directory
    imdir, imname = os.path.split(image)

    # Create destination directory
    png_dir = os.path.join(imdir, "pngraw")
    if not os.path.isdir(png_dir):
        os.makedirs(png_dir)

    png_dir = os.path.join(png_dir, subdir)
    if not os.path.isdir(png_dir):
        os.makedirs(png_dir)

    # Handle Bias and Flat images
    if 'Bias' in imname or 'Flat' in imname:
        out_suffix = '.png'
    else:
        out_suffix = '_all.png'
    # Handle gzipped files
    if imname.endswith("gz"):
        outfile = imname.replace(".fits.gz", out_suffix)
    else:
        outfile = imname.replace(".fits", out_suffix)
    outfig = os.path.join(png_dir, outfile)

    if not os.path.isfile(outfig):

        logger.info("Plotting raw %s %s image of %s: %s" %
                    (imtype, filt, name, image))

        corners = {
            "g": [1, 1023, 1, 1023],
            "i": [1, 1023, 1024, 2045],
            "r": [1024, 2045, 1024, 2045],
            "u": [1024, 2045, 1, 1023]
        }

        pltstd = 100.
        for b in corners:
            c, lo, hi = sigmaclip(d[corners[b][2]+150:corners[b][3]-150,
                                    corners[b][0]+150:corners[b][1]-150],
                                  low=2.5, high=2.5)
            std = c.std()
            mid = c.mean()
            d[corners[b][2]:corners[b][3], corners[b][0]:corners[b][1]] -= mid
            if 'bias' in subdir and 'r' in b:
                pltstd = std
            elif 'dome' in subdir or 'twilight' in subdir:
                if std > pltstd:
                    pltstd = std
            else:
                if 'r' in b:
                    if std > pltstd:
                        pltstd = std
            if verbose:
                print("%s %.2f %.2f %.2f" % (b, mid, std, pltstd))

        plt.imshow(d, vmin=-pltstd, vmax=2.*pltstd,
                   cmap=plt.get_cmap('Greys_r'))
        if 'FOCUS' in imtype.upper():
            if ut_id is not None:
                plt.title("{%s} %.2f %s %s-band [%ds] " %
                          (imtype, focpos, ut_id, filt, exptime))
            else:
                plt.title("{%s} %.2f %s-band [%ds] " %
                          (imtype, focpos, filt, exptime))
        else:
            if ut_id is not None:
                plt.title("{%s} %s %s %s-band [%ds] " %
                          (imtype, ut_id, name, filt, exptime))
            else:
                plt.title("{%s} %s %s-band [%ds] " %
                          (imtype, name, filt, exptime))
        plt.colorbar()
        logger.info("As %s", outfig)
        plt.savefig(outfig)
        plt.close()
        if verbose:
            print(outfig)
    else:
        if verbose:
            logger.info("Exists: %s", outfig)


def reduce_on_the_fly(photdir, nocopy=False, proc_na=False, do_phot=False,
                      local=False, one_pass=False):
    """
    Waits for new images to appear in the directory to trigger their
    incremental reduction as well.
    """

    # Current time to check against sun_rise
    now = Time(datetime.utcnow())
    p60 = astroplan.Observer.at_site(sedm_cfg['observatory']['name'])
    sun_rise = p60.sun_rise_time(now, which='next')
    logger.info("Run until sun rise at %s", sun_rise.iso)

    # Do we have files yet?
    whatf = os.path.join(photdir, 'rcwhat.list')
    while not os.path.isfile(whatf) and now < sun_rise:
        # Wait 10 minutes
        logger.info("No rcwhat.list file yet, waiting 10 min...")
        time.sleep(600)
        # Check our current time
        now = Time(datetime.utcnow())
        if now > sun_rise:
            logger.warning("Waited for sun rise and no rcwhat file appeared!")
            return
    # Link rcwhat.txt
    if not os.path.islink(os.path.join(photdir, 'rcwhat.txt')):
        os.symlink(os.path.join(photdir, 'rcwhat.list'),
                   os.path.join(photdir, 'rcwhat.txt'))

    # list of raw plots made
    raw_plot_list = []
    bias_done = False
    domes_done = False
    twilights_done = False
    # Wait for an acquisition
    with open(whatf, 'r') as wtf:
        whatl = wtf.readlines()
    acqs = [wl for wl in whatl if 'ACQ' in wl]
    n_wait = 0
    # wait until we have an acquisition
    while len(acqs) <= 0 and now < sun_rise:
        # loop over entries in rcwhat file
        for wl in whatl:
            fl = wl.split()[0]
            utid = "_".join(fl.split("_")[1:]).split(".")[0]
            # plot new ones
            if fl not in raw_plot_list:
                plot_raw_image(os.path.join(photdir, fl), ut_id=utid)
                raw_plot_list.append(fl)
        if n_wait >= 10:
            logger.info("No acquisition for 10 min (bright or weather), "
                        "check again in 60 sec...")
            n_wait = 0
        else:
            n_wait += 1

        time.sleep(60)

        # re-check rcwhat file
        with open(whatf, 'r') as wtf:
            whatl = wtf.readlines()
        # look for ACQs, biases, domes, twilights (complete when focusing)
        acqs = [wl for wl in whatl if 'ACQ' in wl]
        bias = [wl for wl in whatl if 'bias' in wl]
        dome = [wl for wl in whatl if 'dome' in wl]
        focus = [wl for wl in whatl if 'FOCUS' in wl]
        if len(bias) >= 20 and not bias_done:   # we have our biases
            rcred.create_masterbias(phot_dir)
            bias_done = True
        if len(dome) >= 40 and not domes_done:  # we have our domes
            rcred.create_masterflat(phot_dir)
            domes_done = True
        if len(focus) > 0 and not twilights_done:   # we have our eve twilights
            rcred.create_masterflat(phot_dir, twilight=True)
            twilights_done = True
        # Check our current time
        now = Time(datetime.utcnow())
        # if the night is over, process cals anyway
        if now > sun_rise:
            if not bias_done:
                rcred.create_masterbias(phot_dir)
            if not domes_done:
                rcred.create_masterflat(phot_dir)
            if not twilights_done:
                rcred.create_masterflat(phot_dir, twilight=True)
            logger.warning("Waited until sun rise and no ACQ appeared!")
            return
    # end wait for ACQs while loop

    # Make sure required cals were made
    logger.info("Re-checking cals before proceeding")
    if not bias_done:
        rcred.create_masterbias(phot_dir)
    if not domes_done:
        rcred.create_masterflat(phot_dir)
    if not twilights_done:
        rcred.create_masterflat(phot_dir, twilight=True)

    logger.info("We have acquired now, so let's reduce some data!")

    # Get the current the number of files
    nfiles = []
    logger.info("Starting the on-the-fly reduction for directory %s." % photdir)

    dayname = os.path.basename(photdir)

    now = Time(datetime.utcnow())

    if not nocopy:
        # Make destination directory
        cmd = "ssh -l grbuser transient.caltech.edu mkdir " \
              "/scr3/mansi/ptf/p60phot/fremling_pipeline/sedm/reduced/%s" % \
              dayname
        logger.info(cmd)
        subprocess.call(cmd, shell=True)

    phot_zp = {'u': None, 'g': None, 'r': None, 'i': None}
    # Run this loop until sun rise.
    n_wait = 0
    while now < sun_rise:
        # list of all RC image files
        nfilesnew = glob.glob(os.path.join(photdir, "rc*[0-9].fits"))

        if len(nfilesnew) == len(nfiles):
            if n_wait > 10:
                if one_pass:
                    logger.info("One pass requested, exiting loop")
                    return
                else:
                    logger.info("No new image after %d waits, waiting 30s"
                                % n_wait)
            time.sleep(30)
            n_wait += 1
        # we got some new files
        else:
            n_wait = 0
            new = [ff for ff in nfilesnew if ff not in nfiles]  # list of new
            new.sort()
            logger.info("Detected %d new incoming files in the last 30s." %
                        len(new))
            for n in new:
                # Make sure imgtype is available
                if not fitsutils.has_par(n, "IMGTYPE"):
                    print("Image", n, "Does not have an IMGTYPE")
                    time.sleep(0.5)
                    if not fitsutils.has_par(n, "IMGTYPE"):
                        print("Image", n, "STILL Does not have an IMGTYPE")
                        continue
                # Make a plot of image
                imtype = fitsutils.get_par(n, "IMGTYPE")
                req_id = fitsutils.get_par(n, "REQ_ID")
                imname = os.path.basename(n).replace(".fits", "")
                utid = "_".join(imname.split("_")[1:])
                plot_raw_image(n, ut_id=utid)
                if "SCIENCE" in imtype.upper() or "ACQ" in imtype.upper() or \
                        "STANDARD" in imtype.upper():
                    if fitsutils.get_par(n, "EXPTIME") > 30.:
                        do_cosmic = True
                    else:
                        do_cosmic = False
                    reduced = rcred.reduce_image(n, cosmic=do_cosmic)
                    # perform quick photometry if requested
                    if do_phot:
                        for rf in reduced:
                            if fitsutils.get_par(rf, "ONTARGET"):
                                target_object = fitsutils.get_par(rf, "OBJECT")
                                target_filter = target_object.split()[-1]
                                target_name = target_object.split()[0]
                                logger.info(
                                    "Getting quick %s-band mag for %s in %s" %
                                    (target_filter, target_name, rf))
                                target_mag, target_magerr, std_zp = \
                                    get_target_mag(rf, zeropoint=phot_zp)
                                if target_mag is None or target_magerr is None:
                                    logger.warning("Quick mag failed!")
                                else:
                                    logger.info("Quick MAG = %.3f +- %.3f" %
                                                (target_mag, target_magerr))
                                if std_zp is not None:
                                    logger.info("Quick MAG_ZP: %.3f" % std_zp)
                                    if phot_zp[target_filter] is None:
                                        phot_zp[target_filter] = std_zp
                    # end do_phot
                    if not nocopy:
                        # Copy them to transient
                        for r in reduced:
                            toks = os.path.basename(r).split('_')
                            toks[-1] = toks[-1].split('.')[0]
                            # Do the filters match?
                            if toks[-2] == toks[-1]:
                                cmd = "scp %s grbuser@transient.caltech.edu:" \
                                      "/scr3/mansi/ptf/p60phot/" \
                                      "fremling_pipeline/sedm/reduced/%s/" % \
                                      (r, dayname)
                                subprocess.call(cmd, shell=True)
                                logger.info(cmd)
                                logger.info("Successfully copied the image: %s"
                                            % r)
                                # push to slack
                                png_dir = os.path.dirname(r) + '/png/'
                                basename = os.path.basename(r).split('.fits')[0]
                                imgf = png_dir + basename + '.png'
                                title = "RC image: %s | %s" % (basename, imtype)
                                if slack is not None and not local:
                                    try:
                                        slack.push_image(imgf, caption="",
                                                         title=title,
                                                         channel=SLACK_CHANNEL)
                                    except json.decoder.JSONDecodeError:
                                        print("json error, cannot push %s"
                                              % imgf)
                                else:
                                    print("Cannot push: %s" % imgf)
                    # end if not nocopy
                    else:
                        logger.info("Skipping copies to transient")

                    if "SCIENCE" in imtype.upper():
                        t_now = datetime.now()
                        stat_str = "Complete %4d%02d%02d %02d_%02d_%02d" % (
                            t_now.year, t_now.month, t_now.day,
                            t_now.hour, t_now.minute, t_now.second)
                        if not local:
                            update_fritz_status(request_id=req_id,
                                                status=stat_str)
                        else:
                            print('Local mode: not updating fritz')
                elif "POINTING" in imtype.upper():
                    if fitsutils.get_par(n, "EXPTIME") > 30.:
                        do_cosmic = True
                    else:
                        do_cosmic = False
                    reduced = rcred.reduce_image(n, cosmic=do_cosmic)
                    for r in reduced:
                        # push to slack
                        png_dir = os.path.dirname(r) + '/png/'
                        basename = os.path.basename(r).split('.')[0]
                        imgf = png_dir + basename + '.png'
                        title = "RC image: %s | %s" % (basename, imtype)
                        if slack is not None:
                            # only push r-band where ref pixel is
                            if '_r.png' in imgf and not local:
                                slack.push_image(imgf, caption="",
                                                 title=title,
                                                 channel=SLACK_CHANNEL)
                        else:
                            print("Cannot push: %s" % imgf)
                elif "NA" in imtype.upper() and proc_na:
                    if fitsutils.get_par(n, "EXPTIME") > 30.:
                        do_cosmic = True
                    else:
                        do_cosmic = False
                    _ = rcred.reduce_image(n, cosmic=do_cosmic)
        # Check for focus plots
        focus_plots = glob.glob(os.path.join(photdir, "rcfocus*.png"))
        for fp in focus_plots:
            bn = os.path.basename(fp)
            lbn = os.path.join(photdir, "pngraw/focus", bn)
            if not os.path.islink(lbn):
                os.symlink(fp, lbn)
                if not local:
                    slack.push_image(fp, caption="RC FOCUS", title=bn,
                                     channel=SLACK_CHANNEL)
        # Get new time
        now = Time(datetime.utcnow())
        logger.info("Time is now %s", now.iso)
        # Update file count
        nfiles = nfilesnew

    # Process twilights, if we have not done so at the beginning of the night
    if not twilights_done:
        rcred.create_masterflat(phot_dir, twilight=True)

    logger.info("End of night because sun is up!")


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="""
        Performs on-the-fly RC reduction
        """, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-d', '--photdir', type=str, dest="photdir",
                        help='Fits directory file with tonight images.',
                        default=None)
    parser.add_argument('-n', '--nocopy', action="store_true",
                        help='do not copy to transient', default=False)
    parser.add_argument('-p', '--proc_na', action="store_true",
                        help='process NA image types', default=False)
    parser.add_argument('-l', '--local', action="store_true",
                        help='process locally', default=False)
    parser.add_argument('-o', '--one_pass', action="store_true",
                        help='make only one pass through images', default=False)

    args = parser.parse_args()

    if args.photdir is None:
        timestamp = datetime.isoformat(datetime.utcnow())
        timestamp = timestamp.split("T")[0].replace("-", "")
        pdir = os.path.join(_photpath, timestamp)
    else:
        pdir = args.photdir

    phot_dir = os.path.abspath(pdir)

    print("Reducing RC data in", phot_dir)
    logger.info("Reducing RC data in %s", phot_dir)

    reduce_on_the_fly(phot_dir, nocopy=args.nocopy, proc_na=args.proc_na,
                      local=args.local, one_pass=args.one_pass)

    ntopgz, nredgz = gzip_fits_files(phot_dir)
    logger.info("Gzipped %d top-level and %d reduced fits files" %
                (ntopgz, nredgz))

    day_name = os.path.basename(phot_dir)
    logger.info("Concluding RC image processing for %s." % day_name)
