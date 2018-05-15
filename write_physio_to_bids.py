import re
import os
from math import ceil
from bids.grabbids import BIDSLayout
import json
import csv
import gzip
import argparse

def convert_time(acqtime):
    # convert hours-minutes-seconds.mikliseconds format to ms
    return int(ceil(1000*((float(acqtime[0:2])*60 + \
        float(acqtime[2:4]))*60 + float(acqtime[4:]))))

def create_filebase(boldfile):
    return re.search('(.*)_bold.ni*', boldfile).group(1)

def read_physio_7T(fbase, ext):
    with open(fbase + ext) as f:
        lines = f.readlines()
    MPCUTime = [0,0]
    MDHTime = [0,0]
    for l in lines:
        if '_SAMPLES_PER_SECOND' in l:
            scaninfo = re.search('5002(.*)6002', l).group(1)
            samprate = float(re.search('_SAMPLES_PER_SECOND = ([1-9][0-9]*)', scaninfo).group(1))
            physio = re.search('6002 (.*)5002', l).group(1).split(' ')
            physio = [v for v in physio if v != '5000' or v != '6000']
        if 'MPCUTime' in l:
            ls = l.split()
            if 'LogStart' in l:
                MPCUTime[0]= int(ls[1])
            elif 'LogStop' in l:
                MPCUTime[1]= int(ls[1])
        if 'MDHTime' in l:
            ls = l.split()
            if 'LogStart' in l:
                MDHTime[0]= int(ls[1])
            elif 'LogStop' in l:
                MDHTime[1]= int(ls[1])
    return MDHTime, samprate, physio

def write_physio_to_bids(physio_dir,bids_dir):
    # read the acqtimes out of the bids dataset use these to match with the physio files
    l=BIDSLayout(bids_dir)
    files = l.get(type='bold', return_type='file', extensions='.nii.gz')
    acqtimes = {}
    endtimes = {}
    for f in files:
        acqtime=convert_time(l.get_metadata(f)['time']['samples']['AcquisitionTime'][0])
        if acqtime not in acqtimes.keys():
            acqtimes[acqtime] = [f]
            endtimes[acqtime] = [convert_time(l.get_metadata(f)['time']['samples']['AcquisitionTime'][0])]
        else:
            acqtimes[acqtime].append(f)
            endtimes[acqtime].append(convert_time(l.get_metadata(f)['time']['samples']['AcquisitionTime'][0]))
        if l.get_metadata(f)['MagneticFieldStrength']!=6.98:
            print("Scanners other than the Siemens 7T are not currently supported")
            raise(NameError)
    # read in physio files and match based on acqtime time and date
    # to functional data
    files = set([f[0:-4] for f in os.listdir(physio_dir) if '.puls' in f])
    for f in files:
        ctime, csf, cardiac = read_physio_7T(physio_dir + f, 'puls')
        rtime, rsf, respiratory = read_physio_7T(physio_dir + f, 'resp')
        acqmatches = [fname for key, fname in acqtimes.items() if key-ctime[0]>0 and ctime[1]-endtimes[key][0]>0]
        if len(acqmatches)>0:
            for image in acqmatches[0]:
                # if matched find the difference between the MDHTime and the Acquisition time as start time
                # https://cfn.upenn.edu/aguirre/wiki/public:pulse-oximetry_during_fmri_scanning
                imtime = convert_time(l.get_metadata(image)['time']['samples']['AcquisitionTime'][0])
                filematches = create_filebase(image)
                cardiac_json = {'SamplingFrequency':csf,
                                'StartTime':(ctime[0] - imtime)/1000.0,
                                'Columns':["cardiac"]}
                with open(filematches + '_recording-cardiac_physio.json', 'w+') as fp:
                    json.dump(cardiac_json, fp)
                with gzip.open(filematches + '_recording-cardiac_physio.tsv.gz', 'wt+') as tsv:
                    writer = csv.writer(tsv, delimiter='\t')
                    for val in cardiac:
                        try:
                            writer.writerow([int(val)])
                        except:
                            continue
                resp_json = {'SamplingFrequency':rsf,
                                'StartTime':(rtime[0] - imtime)/1000.0,
                                'Columns':["respiratory"]}
                with open(filematches + '_recording-respiratory_physio.json', 'w+') as fp:
                    json.dump(resp_json, fp)
                with gzip.open(filematches + '_recording-respiratory_physio.tsv', 'wt+') as tsv:
                    writer = csv.writer(tsv, delimiter='\t')
                    for val in respiratory:
                        try:
                            writer.writerow([int(val)])
                        except:
                            continue

if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Convert Siemens 7T physio data to BIDS format')
    parser.add_argument('--physio_dir', '-p', metavar='physio', nargs=1,
                        help='directory holding the physio files')
    parser.add_argument('--bids_dir', '-b', metavar='bids', nargs=1,
                        help='directory holding the bids dataset')

    args = parser.parse_args()
    write_physio_to_bids(args.physio_dir[0], args.bids_dir[0])
    print("Conversion complete")