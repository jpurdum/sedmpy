import os
import requests
import json
import argparse
import shutil
from marshals.interface import api

import sedmpy_version

with open(os.path.join(sedmpy_version.CONFIG_DIR, 'marshals.json')) as data_file:
    params = json.load(data_file)

token = params['marshals']['fritz']['token']

BASEURL = 'https://fritz.science/'                     # Fritz base url

API_KEY = "54916f1700966b3bd325fc1189763d86512bda1d"     # TNS API Key

# TNS URLs for real uploads
TNS_BASE_URL = "https://www.wis-tns.org/api/"
upload_url = "https://www.wis-tns.org/api/file-upload"
report_url = "https://www.wis-tns.org/api/bulk-report"
reply_url = "https://www.wis-tns.org/api/bulk-report-reply"

TNS_HEADERS = {
    'User-Agent': 'tns_marker{"tns_id":48869, "type":"bot",'
                  ' "name":"ZTF_Bot1"}'
}

# SANDBOX URLs for TNS upload trials
# SAND_TNS_BASE_URL = "https://sandbox.wis-tns.org/api/"
# SAND_upload_url = "https://sandbox.wis-tns.org/api/"
# SAND_report_url = "https://sandbox.wis-tns.org/api/bulk-report"
# SAND_reply_url = "https://sandbox.wis-tns.org/api/bulk-report-reply"


def get_source_api_comments(ztf_name):
    """ Info : Query a single source, takes input ZTF name
        Returns : comments for the source
    """
    url = BASEURL+'api/sources/'+ztf_name+'/comments'
    resp = api('GET', url)
    if 'success' in resp['status']:
        rdata = resp['data']
    else:
        print('Unable to retrieve comments for %s' % ztf_name)
        print(resp)
        rdata = None
    return rdata


def get_iau_name(ztf_name):

    """ Info : Query the TNS name for any source
        Input : ZTFname
        Returns : ATname
    """

    url = BASEURL + 'api/alerts_aux/' + ztf_name
    resp = api('GET', url)
    if 'success' in resp['status']:
        return resp["data"]["cross_matches"]["TNS"]
    else:
        print('Unable to retrieve TNS name from fritz for %s' % ztf_name)
        print(resp)
        return None


def get_tns_name(ztf_name):
    """ Info : Query the TNS for name
        Input : ZTFname
        Returns : ATname
    """
    req_data = {
        "ra": "",
        "dec": "",
        "radius": "",
        "units": "",
        "objname": "",
        "objname_exact_match": 0,
        "internal_name": ztf_name,
        "internal_name_exact_match": 0,
        "objid": ""
    }

    data = {'api_key': API_KEY, 'data': json.dumps(req_data)}

    response = requests.post('https://www.wis-tns.org/api/get/search',
                             headers=TNS_HEADERS, data=data).json()
    if response['data']['reply']:
        tns_name = response['data']['reply'][0]['objname']
    else:
        tns_name = None

    # json.loads(response.text)['data']['reply'][0]['objname']
    return tns_name


def get_classification(ztf_name):

    """ Info : Query the classification and classification date for any source
        Input : ZTFname
        Returns : Classification and Classification date
        Comment : You need to choose the classification
                if there are multiple classifications
    """
    classification = None
    classification_date = None

    url = BASEURL + 'api/sources/' + ztf_name + '/classifications'
    resp = api('GET', url)
    if 'success' in resp['status']:

        output = resp['data']
        if len(output) < 1:
            classification = "No Classification found"
            classification_date = "None"

        if len(output) == 1:

            classification = resp['data'][0]['classification']
            classification_date = resp['data'][0]['created_at'].split('T')[0]

        if len(output) > 1:

            for si in range(len(output)):

                author = resp['data'][si]['author_name']
                clss = resp['data'][si]['classification']
                classify_date = resp['data'][si]['created_at']

                if author == 'sedm-robot':
                    classification = clss
                    classification_date = classify_date
    else:
        print('Unable to retrieve classifications for %s' % ztf_name)
        print(resp)

    return classification, classification_date


def get_redshift(ztf_name):

    """ Info : Query the redshift for any source
        Input : ZTFname
        Returns : redshift
    """

    url = BASEURL + 'api/sources/' + ztf_name
    resp = api('GET', url)

    if 'success' in resp['status']:

        redshift = resp['data']['redshift']

        if redshift is None:
            redshift = "No redshift found"
    else:
        print('Unable to retrieve redshift for %s' % ztf_name)
        print(resp)
        redshift = None

    return redshift


def get_tns_information(ztf_name):

    iau = get_iau_name(ztf_name)

    if not iau:

        iau = get_tns_name(ztf_name)

        if not iau:

            iau = "Not reported to TNS"

    else:
        iau = iau[0]['name']

    clss = get_classification(ztf_name)

    if clss[1] == 'None':
        clss = "Not classified yet"

    else:
        clss = ('Classification: ' + str(clss[0]) + ',' +
                ' Classification date: ' + str(clss[1]))

    redshift = get_redshift(ztf_name)

    if redshift is None:
        redshift = "No redshift found"

    else:
        redshift = ('redshift:'+str(redshift))

    return ztf_name, iau, clss, redshift


def get_spectrum_api(spectrum_id):
    """ Info : Query all spectra corresponding to a source, takes input ZTF name
        Returns : list of spectrum jsons
    """
    url = BASEURL + 'api/spectra/' + str(spectrum_id)
    resp = api('GET', url)
    if 'success' in resp['status']:
        return resp['data']
    else:
        print('Unable to retrieve spectrum with id: %d' % spectrum_id)
        print(resp)
        return None


def get_all_spectra(ztf_name):

    url = BASEURL + 'api/sources/' + ztf_name + '/spectra'
    resp = api('GET', url)
    if 'success' in resp['status']:
        return resp['data']['spectra']
    else:
        print('Unable to retrieve all spectra for %s' % ztf_name)
        print(resp)
        return None


def get_all_spectra_id(ztf_name):
    """ Info : Query all spectra corresponding to a source, takes input ZTF name
        Returns : list of spectrum jsons
    """

    spec_id = []

    spectra = get_all_spectra(ztf_name)

    if spectra is not None:
        for spec in spectra:
            spec_id.append(spec['id'])
    else:
        print('No %s spectra retrieved for all ids' % ztf_name)

    return spec_id


def get_required_spectrum_id(ztf_name, spec_file):

    spec_id = None

    specfn = os.path.basename(spec_file)

    spectra = get_all_spectra(ztf_name)

    if spectra is not None:

        for spec in spectra:

            if specfn in spec['original_file_filename']:
                spec_id = spec['id']
    else:
        print('No %s spectra retrieved for id in file %s' % (ztf_name, specfn))

    return spec_id


def write_ascii_file(ztf_name, specfl, path=None):

    specfn = None

    if specfl is None:
        print("ERROR: no spectrum file")

    else:
        with open(specfl) as f:
            header = {line.split(':', 1)[0][1:].strip():
                      line.split(':', 1)[-1].strip()
                      for line in f if line[0] == '#'}

        inst = header['INSTRUME']

        if inst == 'SEDM-P60':

            specfn = (ztf_name + '_' + str(header['OBSDATE']) +
                      '_SEDM.ascii')

            shutil.copy(specfl, os.path.join(path, specfn))

        else:
            print('ERROR: not an SEDM spectrum!')
            specfn = None

    return specfn


def post_comment(ztf_name, text):

    data = {"text": text}

    url = BASEURL + 'api/sources/%s/comments' % ztf_name

    resp = api('POST', url, data=data)

    if 'success' in resp['status']:
        pass
    else:
        print('Unable to post %s comment: %s' % (ztf_name, text))
        print(resp)

    return resp


def pprint(*pars, **kwargs):
    """
    slightly more convenient function instead of print(get_pprint)

    params:
        *pars (parameters to pass to get_pprint)
        **kwargs (keyword arguments to pass to get_pprint)
    """
    print(get_pprint(*pars, **kwargs))


def get_pprint(item, indent=0, tab=' '*4, maxwidth=float('inf')):
    """
    it's just like 'from pprint import pprint', except instead of
    having dictionaries use hanging indents dependent on the length
    of their key, if the value is a list or dict it prints it indented
    by the current indent plus tab

    params:
        item <di or li> (the thing to be printed)
        indent <int> (the number of times it's been indented so far)
        tab <str> (how an indent is represented)
        maxwidth <int> (maximum characters per line in ouptut)

    returns:
        result <str>
    """
    def get_pprint_di(di, indent, tab=' '*4):
        """
        pprints a dictionary

        params:
            di <dict>
            indent <int> (the number of indents so far)

        returns:
            di_str <str>
        """
        di_str = ''
        for i, (key, item) in enumerate(di.items()):
            di_str += tab*indent
            di_str += repr(key) + ': ' + get_pprint(item, indent, tab)
            if i+1 < len(di):
                # everything until the last item has a trailing comma
                di_str += ',\n'
            else:
                di_str += '\n'
        return di_str

    def get_pprint_li(li, indent, tab=' '*4):
        """
        pprints a list

        params:
            li <list>
            indent <int> (the number of indents so far)

        returns:
            current_result <str>
        """
        li_str = ''
        for i, item in enumerate(li):
            li_str += tab*indent
            pprint(item, indent, tab)
            if i+1 < len(li):
                li_str += ',\n'
            else:
                li_str += '\n'
        return li_str

    result = ''
    if isinstance(item, dict):
        result += '{\n'
        result += get_pprint_di(item, indent+1, tab)
        result += tab*indent + '}'
    elif isinstance(item, list):
        result += '[\n'
        result += get_pprint_li(item, indent+1, tab)
        result += tab*indent + ']'
    else:
        result += repr(item)

    # this gets rid of too-long lines, but only supports space tabs
    lines = result.split('\n')
    for i, line in enumerate(lines):
        while max([len(li) for li in line.split('\n')]) > maxwidth:
            tabs = line[:-len(line.lstrip())]
            if len(tabs) > maxwidth - 8:
                break  # giving up
            line = line[:78] + '\\\n' + tabs + 2*tab + line[78:]
            lines[i] = line
    result = '\n'.join(lines)

    return result


def get_tns_classification_id(classification):

    class_ids = {'Afterglow': 23, 'AGN': 29, 'CV': 27, 'Galaxy': 30, 'Gap': 60,
                 'Gap I': 61, 'Gap II': 62, 'ILRT': 25, 'Kilonova': 70,
                 'LBV': 24, 'M dwarf': 210, 'Nova': 26, 'Novae': 26, 'QSO': 31,
                 'SLSN-I': 18, 'SLSN-II': 19, 'SLSN-R': 20, 'SN': 1, 'I': 2,
                 'Type I': 2, 'I-faint': 15, 'I-rapid': 16, 'Ia': 3,
                 'Ia-norm': 3, 'Ia-91bg': 103, 'Ia-91T': 104, 'Ia-CSM': 106,
                 'Ia-pec': 100, 'Ia-SC': 102, 'Ia-02cx': 105, 'Ib': 4,
                 'Ib-norm': 4, 'Ib-Ca-rich': 8, 'Ib-pec': 107, 'Ib/c': 6,
                 'SN Ibn': 9, 'Ic': 5, 'Ic-norm': 5, 'Ic-BL': 7, 'Ic-pec': 108,
                 'II': 10, 'Type II': 10, 'II-norm': 10, 'II-pec': 110,
                 'IIb': 14, 'IIL': 12, 'IIn': 13, 'IIn-pec': 112, 'IIP': 11,
                 'SN impostor': 99, 'Std-spec': 50, 'TDE': 120, 'Varstar': 28,
                 'WR': 200, 'WR-WC': 202, 'WR-WN': 201, 'WR-WO': 203,
                 'Other': 0}

    # keys = np.array(class_ids.keys())
    for keys in class_ids:
        if keys == classification:
            classkey = class_ids[keys]
            return classkey


def get_tns_instrument_id(inst):

    inst_ids = {'DBSP': 1, 'ALFOSC': 41, 'LRIS': 3, 'DIS': 70, 'SEDM': 149,
                'SPRAT': 156, 'GMOS': 6, 'Lick-3m': 10, 'LFC': 2, 'TSPEC': 109}

    if inst in inst_ids:
        return inst_ids[inst]
    else:
        return None


class TNSClassificationReport:
    def __init__(self):
        self.name = ''
        self.fitsName = ''
        self.asciiName = ''
        self.classifierName = ''
        self.classificationID = ''
        self.redshift = ''
        self.classificationComments = ''
        self.obsDate = ''
        self.instrumentID = ''
        self.expTime = ''
        self.observers = ''
        self.reducers = ''
        self.specTypeID = ''
        self.spectrumComments = ''
        self.groupID = ''
        self.spec_proprietary_period_value = ''
        self.spec_proprietary_period_units = ''

    def fill(self):
        spectrumdict = {
            'obsdate': self.obsDate,
            'instrumentid': self.instrumentID,
            'exptime': self.expTime,
            'observer': self.observers,
            'reducer': self.reducers,
            'spectypeid': self.specTypeID,
            'ascii_file': self.asciiName,
            'fits_file': self.fitsName,
            'remarks': self.spectrumComments,
            'spec_proprietary_period': self.spec_proprietary_period_value}

        classification_dict = {
            'classification_report': {
                '0': {
                    'name': self.name,
                    'classifier': self.classifierName,
                    'objtypeid': self.classificationID,
                    'redshift': self.redshift,
                    'groupid': self.groupID,
                    'remarks': self.classificationComments,
                    'spectra': {
                        'spectra-group': {
                            '0': spectrumdict
                        }
                    }
                }
            }
        }

        return classification_dict

    def classification_json(self):
        return json.dumps(self.fill())


def upload_to_tns(filename, base_url=upload_url, api_key=API_KEY,
                  filetype='ascii'):
    """
    uploads a file to TNS and returns the response json
    """
    url = base_url
    data = {'api_key': api_key}

    if filetype == 'ascii':
        files = [('files[]', (filename, open(filename), 'text/plain'))]

    elif filetype == 'fits':
        files = [('files[0]', (filename, open(filename, 'rb'),
                               'application/fits'))]
    else:
        files = None

    if files is not None:
        response = requests.post(url, headers=TNS_HEADERS, data=data,
                                 files=files)
        try:
            return response.json()
        except:
            print(url, data, files, response.content, sep='\n')
            return False
    else:
        return False


def tns_classify(classification_report, base_url=report_url, api_key=API_KEY):
    """
    submits classification report to TNS and returns the response json
    """
    url = base_url
    data = {'api_key': api_key,
            'data': classification_report.classification_json()}
    resp = requests.post(url, headers=TNS_HEADERS, data=data).json()
    if not resp:
        return False

    res_code = resp['id_code']
    reprt_id = resp['data']['report_id']
    print("ID:", reprt_id)
    print(res_code, resp['id_message'], "reporting finished")
    if res_code == 200:
        return reprt_id
    else:
        print("Result reporting didn't work")
        pprint(resp)
        print("re-submit classification, but don't re-upload files")
        return False


def tns_feedback(reprt_id):
    data = {'api_key': API_KEY, 'report_id': reprt_id}
    resp = requests.post(TNS_BASE_URL + 'bulk-report-reply',
                         headers=TNS_HEADERS, data=data).json()
    feedback_code = resp['id_code']
    print(feedback_code, resp['id_message'], "feedback finished")
    if feedback_code == 200:
        return True
    elif feedback_code == 404:
        print("probably OK")
        # print("Waiting and retrying...")
        # sleep(2)
        # try:
        #    return tns_feedback(reprt_id)
        # except KeyboardInterrupt:
        #    return False
        return True
    elif feedback_code == 400:
        print(resp)
        return False
    else:
        # error receiving the feedback from TNS about the upload
        print("Something went wrong with the feedback, but the report may",
              "still have been fine?")
        return False


def sedm_tns_classify(spec_file, ztfname=None, iau_name=None, testing=False):
    """Verify the input source, prepare a classification report and
    upload to TNS"""

    if not os.path.exists(spec_file):
        print("ERROR: File not found!: %s" % spec_file)
        return False

    with open(spec_file) as f:
        header = {line.split(':', 1)[0][1:].strip():
                  line.split(':', 1)[-1].strip()
                  for line in f if line[0] == '#'}

    if ztfname is None:
        ztfname = header['NAME']

    s_comments = get_source_api_comments(ztfname)
    if s_comments is not None:
        comments = [c['text'] for c in s_comments]
    else:
        return False
    if 'Uploaded to TNS' in comments:
        print("Already uploaded to TNS")
        return False

    if 'Do not upload to TNS' in comments:
        print("TNS upload blocked")
        return False

    info = get_tns_information(ztfname)

    if info[2] == 'Not classified yet':         # Check if classified
        print(info[2])
        return False

    if 'Not reported to TNS' in info[1] and iau_name is None:
        print(info[1])
        return False

    tns_suffix = info[1].split()[0]
    if 'SN' in tns_suffix:
        print('Already classified on TNS: %s' % info[1])
        return False

    class_date = info[2].split(',')[-1].split(':')[-1].strip()
    classify = info[2].split(',')[0].split(':')[-1].strip()

    # print(info)

    path = os.path.dirname(spec_file)

    spectrum_name = write_ascii_file(ztfname, spec_file, path=path)

    if spectrum_name is None:
        print("No spectrum found")
        return False

    specfile = os.path.join(path, spectrum_name)

    classifiers = 'SNIascore on behalf of the SEDM Team (Caltech) and ' \
                  'the Zwicky Transient Facility (ZTF)'
    source_group = 48  # ZTF source group number

    proprietary_period = '0'
    proprietary_units = "years"
    spec_comments = ''
    classification_comments = ''
    spectype = 'object'
    spectype_id = ['object', 'host', 'sky', 'arcs',
                   'synthetic'].index(spectype) + 1

    obsdate = str((header['UTC']).split('T')[0]) + \
        ' ' + str((header['UTC']).split('T')[1])

    classification_report = TNSClassificationReport()
    if iau_name is None:
        classification_report.name = info[1].split()[-1]
    else:
        classification_report.name = iau_name
    classification_report.fitsName = ''
    classification_report.asciiName = spectrum_name
    classification_report.classifierName = classifiers
    classification_report.classificationID = get_tns_classification_id(classify)
    classification_report.redshift = get_redshift(ztfname)
    classification_report.classificationComments = classification_comments
    classification_report.obsDate = obsdate
    classification_report.instrumentID = get_tns_instrument_id('SEDM')
    classification_report.expTime = (header['EXPTIME'])
    classification_report.observers = 'SEDmRobot'
    classification_report.reducers = (header['REDUCER'])
    classification_report.specTypeID = spectype_id
    classification_report.spectrumComments = spec_comments
    classification_report.groupID = source_group
    classification_report.spec_proprietary_period_value = proprietary_period
    classification_report.spec_proprietary_period_units = proprietary_units

    pprint(classification_report.fill(), tab='  ')

    # ASCII FILE UPLOAD
    if not testing:
        print("\n")
        response = upload_to_tns(specfile)
        print(response)

        if not response:
            print("File upload didn't work")
            print(response)
            return False

        print(response['id_code'], response['id_message'],
              "\nSuccessfully uploaded ascii spectrum")
        # classification_report.asciiName = response['data'][-1]

        report_id = tns_classify(classification_report)
        post_comment(ztfname, 'Uploaded to TNS')
        tns_feedback(report_id)
    else:
        print(classification_report)

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="""

Uploads classification report to the TNS website.

""",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--data_file', type=str, default=None,
                        help='Data file to upload: '
                             '/scr2/sedmdrp/redux/YYYYMMDD/spec_*.txt')
    parser.add_argument('--iau_name', type=str, default=None,
                        help='IAU designation: YYYYabc')
    parser.add_argument('--testing', action="store_true", default=False,
                        help='Do not actually post to TNS (for testing)')
    args = parser.parse_args()

    infile = args.data_file

    # Check input
    if not os.path.exists(infile):
        print("File not found: %s" % infile)
    else:
        print("Uploading from %s" % infile)
        sedm_tns_classify(infile, iau_name=args.iau_name, testing=args.testing)
