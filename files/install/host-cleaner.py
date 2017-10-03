import baker
import datetime
import os
import requests
import socket
import json
from foreman.client import Foreman


class ForemanProxy(object):
    def __init__(self, url, auth=None, verify=False):
        self.session = requests.Session()
        self.url = url
        self.session.verify = verify
        if auth is not None:
            self.session.auth = auth

        self.session.headers.update(
        {
            'Accept': 'application/json',
            'Content-type': 'application/json',
        })

        fqdn = socket.getfqdn()
        self.session.cert = ('/var/lib/puppet/ssl/certs/{}.pem'.format(fqdn), '/var/lib/puppet/ssl/private_keys/{}.pem'.format(fqdn))

    def delete_certificate(self, host):
        uri = "/puppet/ca/{}".format(host)
        r = self.session.delete(self.url + uri)
        if r.status_code < 200 or r.status_code >= 300:
            print('Something went wrong: %s' % r.text)
        else:
            print('{} deleted'.format(host))
        return r

    def get_certificates(self):
        uri = "/puppet/ca"
        r = self.session.get(self.url + uri)
        if r.status_code < 200 or r.status_code >= 300:
            print('Something went wrong: %s' % r.text)
        else:
            return r.json()


@baker.command()
def clean_old_certificates(json_file=None):
    # Retrieve config from ENV
    foreman_url = os.environ.get('FOREMAN_URL')
    foreman_user = os.environ.get('FOREMAN_USER')
    foreman_password = os.environ.get('FOREMAN_PASSWORD')
    foreman_proxy_url = "https://{}:{}".format(os.environ.get('FOREMANPROXY_HOST'), os.getenv('FOREMANPROXY_PORT','8443'))

    # connect to Foreman and ForemanProxy
    f=Foreman(foreman_url, (foreman_user, foreman_password))
    fp = ForemanProxy(foreman_proxy_url)

    # Build a certificates list with only hostcert, discarding specific certs used for foreman, puppet, etc ...
    host_pattern = ['ndev', 'nsta', 'nifd', 'npra', 'nifp', 'nhip', 'nifh', 'win']
    if not json_file:
        certs = fp.get_certificates().keys()
    else:
        try:
            with open(json_file) as data_file:
                certs = json.load(data_file)
        except:
            print("Cant't decode json file")
    certs = [cert for cert in certs if any(pattern in cert for pattern in host_pattern)]
    foreman_hosts = []

    # Get all host in foreman
    get_next_page = True
    page = 1
    while get_next_page:
        result = f.index_hosts(per_page="1000", page=str(page))
        if len(result) == 1000:
            page += 1
        else:
            get_next_page = False
        for host in result:
            foreman_hosts.append(host["host"]["name"])

    certs_to_delete = list(set(certs) - set(foreman_hosts))

    for cert in certs_to_delete:
        print(" {} will be deleted".format(cert))
        try:
            fp.delete_certificate(cert)
        except:
            print(" {} couldn't be deleted".format(cert))


@baker.command()
def clean_old_host():

    # Retrieve config from ENV
    foreman_url = os.environ.get('FOREMAN_URL')
    foreman_user = os.environ.get('FOREMAN_USER')
    foreman_password = os.environ.get('FOREMAN_PASSWORD')
    foreman_proxy_url = "https://{}:{}".format(os.environ.get('FOREMANPROXY_HOST'), os.getenv('FOREMANPROXY_PORT','8443'))
    delay = os.getenv('FOREMAN_CLEAN_DELAY', '1')

    #connect to Foreman and ForemanProxy
    f=Foreman(foreman_url, (foreman_user, foreman_password))
    fp = ForemanProxy(foreman_proxy_url)


    #Get the the current date
    currentdate = datetime.datetime.utcnow()

    #check for all host
    get_next_page = True
    page = 1
    while get_next_page:
        result = f.index_hosts(per_page="1000", page=str(page))
        if len(result) == 1000:
            page += 1
        else:
            get_next_page = False
        for host in result:
            #get the la comiple date
            lastcompile = f.show_hosts(id=host["host"]["id"])["host"]["last_compile"]
            #Convert the string date to datetime format
            if lastcompile:
                hostdate = datetime.datetime.strptime(lastcompile,'%Y-%m-%dT%H:%M:%S.%fZ')
                #Get the delta between the last puppet repport and the current date
                elapsed = currentdate - hostdate
                # if the deta is more than $delay days we delete the host
                if elapsed > datetime.timedelta(hours=int(delay)):
                    print "I will destroy the server "+host["host"]["name"]+" because the last report was " +str(lastcompile)
                    #destroy the host in foreman
                    f.destroy_hosts(id=host["host"]["id"])
                    #remove the certificate in puppet
                    fp.delete_certificate(host["host"]["name"])

## Read option
if __name__ == "__main__":
  baker.run()