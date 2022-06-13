import os
import json
import glob
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import sedmpy_version

DEFAULT_TIMEOUT = 5  # seconds

with open(os.path.join(sedmpy_version.CONFIG_DIR, 'marshals.json')) as data_file:
    marshal_cfg = json.load(data_file)

token = marshal_cfg['marshals']['fritz']['token']


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = DEFAULT_TIMEOUT
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


session = requests.Session()
session_headers = {'Authorization': 'token {}'.format(token)}
retries = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[405, 429, 500, 502, 503, 504],
    method_whitelist=["HEAD", "GET", "PUT", "POST", "PATCH"]
)
adapter = TimeoutHTTPAdapter(timeout=5, max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)


def api(method, endpoint, data=None, verbose=False):
    headers = {'Authorization': 'token {}'.format(token)}
    error_dict = {'status': 'Error', 'message': 'AnError', 'data': None}
    try:
        response = session.request(method, endpoint, json=data, headers=headers)
        print('HTTP code: {}, {}'.format(response.status_code, response.reason))
        if response.status_code in (200, 400) and verbose:
            print(response.text)
            # print('JSON response: {}'.format(response.json()))
        ret = response.json()
    except requests.exceptions.RetryError:
        error_dict['message'] = 'RetryError'
        ret = error_dict
    except requests.exceptions.ConnectionError:
        error_dict['message'] = 'ConnectionError'
        ret = error_dict
    except AttributeError:
        error_dict['message'] = 'AttributeError'
        ret = error_dict
    except json.decoder.JSONDecodeError:
        error_dict['message'] = 'JSONDecodeError'
        ret = error_dict

    return ret


def update_status_request(status, request_id, marshal_name, save=False,
                          output_file='', testing=False):
    """
    Function to update the status of any request as long as it has
    not been deleted. The new status will show up on the status section
    of the request on the growth marshal.

    :param status:
    :param request_id:
    :param marshal_name:
    :param save:
    :param output_file:
    :param testing:
    :return:
    """

    # 1. Get the instrument id
    if marshal_name.lower() not in marshal_cfg['marshals']:
        return {"iserror": True, "msg": "Marshal: %s not found in config file"}

    if save:
        if not output_file:
            request_str = str(request_id)
            output_file = os.path.join(marshal_name.lower(), "_", request_str,
                                       ".json")

            if os.path.exists(output_file):
                files = sorted(glob.glob("*_%s_*"))
                if not files:
                    output_file = os.path.join(marshal_name.lower(), "_",
                                               request_str, "_", "1", ".json")
                else:
                    last_file_count = files[-1].split('_')[-1].replace('.json',
                                                                       '')
                    last_file_count = int(last_file_count) + 1
                    output_file = os.path.join(marshal_name.lower(), "_",
                                               request_str, "_",
                                               str(last_file_count),
                                               ".json")
        print("output_file(not used) = %s" % output_file)

    # 2. Create the new status dictionaryCopy
    status_payload = {
        "new_status": status,
        "followup_request_id": request_id
    }

    # 3. Send the update
    if testing:
        print(status_payload)
    else:
        ret = api("POST", marshal_cfg["marshals"][marshal_name]['status_url'],
                  data=status_payload)
        if 'success' in ret['status']:
            print('Status for request %d updated to %s' % (request_id, status))
        else:
            print('Status update failed:\n', ret)
            if "message" in ret:
                ret["iserror"] = ret['message']
            else:
                ret["iserror"] = "Unkown error when posting update"
        return ret


def read_request(request, isfile=True):
    """
    Read an incoming request from external marshal.  All request are expected
    to be in a json format that can be converted to a python dictionary

    :param isfile: Is the request a file
    :param request: Expected type is pathfile,
    :return: dictionary of request
    """

    # 1. If isfile is true then check for the file and assume it is
    # in json format
    print(type(request))
    if isfile and os.path.exists(request):
        try:
            with open(request) as f:
                output = json.load(f)
        except Exception as e:
            output = {'iserror': True,
                      'msg': str(e)}
        return output

    # 2. If it is not a file but a string then assume it is json format
    # and read it in
    if not isfile and isinstance(request, str):
        try:
            output = json.loads(request)
        except Exception as e:
            output = {'iserror': True,
                      'msg': str(e)}
        return output

    # 3. If it is not a file or string but instead a dictionary then just go
    # ahead and return it back
    if not isfile and isinstance(request, dict):
        return request

    # 4. Finally if none of those work then just send back an error message
    return {'iserror': True,
            'msg': "Request is in an unknown format:%s" % type(request)}


def check_field(key, input_dict):
    if key not in input_dict:
        return "Missing key: %s in request" % key
    if not input_dict[key]:
        return "Key: %s is empty or null" % key
    return False


def checker(request, check_source=True, check_followup=True,
            check_program=False, check_user=True,
            check_email=True, check_status=True, check_id=True,
            check_dates=True):

    """
    The following fields are considered to be vital for ingest into the
    SEDm database.  Any fields that are missing or does not pass the
    constraints should result in an invalid request.

    :param request:
    :param check_id:
    :param check_dates:
    :param check_source: Check if there is a source in the request
    :param check_followup: Check if there is a followup type or filters listed
    :param check_program: Check that there is a valid follow-up program
    :param check_user: Check if a valid user is in the request
    :param check_email: Check if a valid email is in the request
    :param check_status: Check that we have a status of new, edit, delete
    :return:
    """
    # Make sure all dictionary keys are lowercase
    if not isinstance(request, dict):
        return {"iserror": True,
                "msg": "Can't check request when not in py dict form"}

    request = dict((k.lower(), v) for k, v in request.items())
    msg_list = []

    # 1. Check that this request comes from a valid source
    if check_source:
        if "origins_url" in request:
            url = request["orgins_url"]
            if not any(x in url for x in marshal_cfg['sources']):
                msg_list.append("Source of request '%s' not regonized" % url)
        else:
            msg_list.append("origins_url missing from request")

    if check_followup:
        followup = False
        filters = False

        if 'followup' in request and request['followup']:
            followup = True
        if 'filters' in request:
            filters = True

        if not followup and not filters:
            msg_list.append("No followup or filters found in request")

    if check_program:
        ret = check_field('programname', request)
        if ret:
            msg_list.append(ret)
        elif request['programname'] not in marshal_cfg['programs']:
            msg_list.append("Progam: %s is not a valid program")

    if check_user:
        ret = check_field('username', request)
        if ret:
            msg_list.append(ret)

    if check_email:
        ret = check_field('email', request)
        if ret:
            msg_list.append(ret)

    if check_status:
        ret = check_field('status', request)
        if ret:
            msg_list.append(ret)
        elif request['status'].lower() not in marshal_cfg['status_types']:
            msg_list.append("Status: %s is not recognized" % request['status'])

    if check_id:
        ret = check_field('requestid', request)
        if ret:
            msg_list.append(ret)

    if check_dates:
        ret = check_field('startdate', request)
        if ret:
            msg_list.append(ret)
        ret = check_field('enddate', request)
        if ret:
            msg_list.append(ret)

    if msg_list:
        return {'iserror': True, 'msg': msg_list}
    else:
        return request


if __name__ == "__main__":
    # print(api("GET", "https://fritz.science/api/allocation"))
    # print(update_status_request("ACCEPTED", 19, "fritz"))
    print(api("GET", "https://fritz.science/api/groups"))
