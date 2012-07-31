#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This script is used to submit multiple certifcate requests and the intended user for the script is the GridAdmin.
This script requests certificates and then approves as well as issues them in bulk (limit of 50 at a time).
"""

import urllib
import httplib
import sys
import ConfigParser
import json
import time
import re
import os
import errno
import getpass
import StringIO
import OpenSSL
import M2Crypto
from optparse import OptionParser


from OpenSSL import crypto
from certgen import *

# Set up Option Parser
#

def parse_args():
    parser = OptionParser()
    parser.add_option(
        '-k',
        '--pkey',
        action='store',
        dest='userprivkey',
        help="Specify Requestor's private key (PEM Format). If not specified will take the value of X509_USER_KEY or $HOME/.globus/userkey.pem"
            ,
        metavar='PKEY',
        default='',
        )
    parser.add_option(
        '-c',
        '--cert',
        action='store',
        dest='usercert',
        help="Specify Requestor's certificate (PEM Format). If not specified will take the value of X509_USER_CERT or $HOME/.globus/usercert.pem"
            ,
        default='',
        metavar='CERT',
        )
    parser.add_option(
        '-f',
        '--hostfile',
        action='store',
        dest='hostfile',
        help='Filename with one hostname per line',
        metavar='HOSTFILE',
        default='hosts.txt',
        )
    parser.add_option(
        '-e',
        '--email',
        action='store',
        dest='email',
        help='Email address to receive certificate',
        metavar='EMAIL',
        )
    parser.add_option(
        '-n',
        '--name',
        action='store',
        dest='name',
        help='Name of user receiving certificate',
        metavar='NAME',
        )
    parser.add_option(
        '-p',
        '--phone',
        action='store',
        dest='phone',
        help='Phone number of user receiving certificate',
        metavar='PHONE',
        )
    parser.add_option(
        '-q',
        '--quiet',
        action='store_false',
        dest='verbose',
        default=True,
        help="don't print status messages to stdout",
        )
    (args, values) = parser.parse_args()

    if not args.phone:
        parser.error("-p/--phone argument required")
    if not args.name:
        parser.error("-n/--name argument required")
    if not args.email:
        parser.error("-e/--email argument required")
    if not args.hostfile:
        parser.error("-f/--hostfile argument required")

    global hostname, domain, email, name, phone, outkeyfile, num_requests, usercert, userprivkey, certdir, hostfile
    certdir = 'certificates'


    hostfile = args.hostfile
    email = args.email
    name = args.name
    phone = args.phone

    if args.userprivkey == '':
        try:
            userprivkey = os.environ["X509_USER_KEY"]
        except:
            userprivkey = str(os.environ["HOME"]) + '/.globus/userkey.pem'
    else:
        userprivkey = args.userprivkey
    
    if os.path.exists(userprivkey):
        pass
    else:
        sys.exit('Unable to locate the private key file:' + userprivkey)
    
    if args.usercert == '':
        try:
            usercert = os.environ["X509_USER_CERT"]
        except:
            usercert = str(os.environ["HOME"]) + '/.globus/usercert.pem'
    else:
        usercert = args.usercert
    
    if os.path.exists(usercert):
        pass
    else:
        sys.exit('Unable to locate the user certificate file:' + usercert)
    
    if os.path.exists(hostfile):
        pass
    else:
        sys.exit('Unable to locate the hostfile:' + hostfile)

    name_no_space = name.replace(' ', '')
    if not name_no_space.isalpha():
        sys.exit('Name should contain only alphabets\n')
    
    phone_num = phone.replace('-', '')
    if not phone_num.isdigit():
        sys.exit("Phone number should contain only numbers and/or '-'\n")

    global host, requrl, appurl, issurl, returl, content_type, Config
    Config = ConfigParser.ConfigParser()
    Config.read('OSGTools.ini')
    host = Config.get('OIMData', 'hostsec')
    requrl = Config.get('OIMData', 'requrl')
    appurl = Config.get('OIMData', 'appurl')
    issurl = Config.get('OIMData', 'issurl')
    returl = Config.get('OIMData', 'returl')
    content_type = Config.get('OIMData', 'content_type')
    return

#################################################


# We make the request here, causing the generation of the CSR and then
# pass the ID returned from the server along. The ID is the key that OIM
# uses for all certificate operations via the API
#

def connect_request(ssl_context, bulk_csr):
    print 'Connecting to server to request certificate...'
    global id
    params = urllib.urlencode({
        'name': name,
        'email': email,
        'phone': phone,
        'csrs': bulk_csr,
        }, doseq=True)
    headers = {'Content-type': content_type,
               'User-Agent': 'OIMGridAPIClient/0.1 (OIM Grid API)'}

    conn = M2Crypto.httpslib.HTTPSConnection(host,
            ssl_context=ssl_context)
    try:
        conn.request('POST', requrl, params, headers)
        response = conn.getresponse()
    except httplib.HTTPException, e:

        print 'Connection to %s failed : %s' % (requrl, e)
        raise e
    data = response.read()
    if not 'OK' in response.reason:
        print response.status, response.reason
        print json.dumps(json.loads(data), sort_keys=True, indent=2)

    conn.close()
    if 'FAILED' in data:
        print json.dumps(json.loads(data), sort_keys=True, indent=2)
        print 'Fatal error: Certificate request has failed. Goc staff has been\nnotified of this issue.'
        print '''You can open a GOC ticket to track this issue by going to
 https://ticket.grid.iu.edu
'''
        sys.exit(1)
    return_data = json.loads(data)
    for (key, value) in return_data.iteritems():
        if 'host_request_id' in key:
            id = value
            print 'Id is:', id


# ID from the request is passed in here via secure connection and the request
# gets approved automatically since it's a bulk request. We also issue the
# certificate (i.e. OIM contacts the CA on our behalf to get the cert) in this
# function
#

def connect_approve(ssl_context):
    print 'Connecting to server to approve certificate...'
    action = 'approve'
    params = urllib.urlencode({'host_request_id': id})
    headers = {'Content-type': content_type,
               'User-Agent': 'OIMGridAPIClient/0.1 (OIM Grid API)'}
    conn = M2Crypto.httpslib.HTTPSConnection(host,
            ssl_context=ssl_context)
    try:
        conn.request('POST', appurl, params, headers)
        response = conn.getresponse()
    except httplib.HTTPException, e:
        print 'Connection to %s failed: %s' % (appurl, repr(e))
        raise e

    if not 'OK' in response.reason:
        print response.status, response.reason
        sys.exit(1)
    data = response.read()
    conn.close()
    if action == 'approve' and 'OK' in data:
        print 'Contacting Server to initiate certificate issuance.'
        newrequrl = Config.get('OIMData', 'issurl')
        conn = M2Crypto.httpslib.HTTPSConnection(host,
                ssl_context=ssl_context)
        try:
            conn.request('POST', newrequrl, params, headers)
            response = conn.getresponse()
        except httplib.HTTPException, e:
            print 'Connection to %s failed: %s' % (newrequrl, e)
            raise e
        data = response.read()
        conn.close()
        if 'FAILED' in data:
            print json.dumps(json.loads(data), sort_keys=True, indent=2)
            print '''Fatal error: Certificate request has failed. Goc staff has been
notified of this issue.
'''
            print 'You can open goc ticket to track this issue by going to https://ticket.grid.iu.edu\n'
            sys.exit(1)
    else:
        sys.exit(0)


# Here's where things have gotten dicey during the testing phase -
# We retrieve the certificate from OIM after it has retrieved it from the CA
# This is where things tend to fall apart - if the delay is to long and the
# request to the CA times out, the whole script operation fails. I'm not
# terribly pleased with that at the moment, but it is out of my hands since
# a GOC staffer has to reset the request to be able to retrieve the
# certificate
#

def write_certs(pkcs7raw, i):
    pkcs7raw = str(pkcs7raw)
    filetype = 'pkcs7-cert'
    fileext = 'pem'
    filename = '%s.%s.%s' % (filetype, id, fileext)
    pem_filename = '%s.%s-%s.%s' % ('host-certs', id, i, 'pem')
    cwd = os.getcwd()
    try:
        os.chdir(certdir)
    except OSError, e:
        sys.exit('''The directory %s does not exist or you cannot access the directory
.Please report the bug to goc@opensciencegrid.org. We would address your issue at the earliest.
 %s''',
                 certdir, e)
    print 'Writing to:', certdir
    try:
        certfile = open(filename, 'w+')
        certfile.write(pkcs7raw)
        certfile.close()
        os.system('openssl pkcs7 -print_certs -in ' + filename
                  + ' -out ' + pem_filename)
        os.remove(filename)
    except OSError, e:
        sys.exit('''You may not have write permission to the directory %s
.Please report the bug to goc@opensciencegrid.org. We would address your issue at the earliest.
 %s''',
                 certdir, e)
    os.chdir(cwd)
    print 'Certificate written to %s \n' % pem_filename
    return


def connect_retrieve():
    iterations = 1
    print 'Issuing certificate...'
    params = urllib.urlencode({'host_request_id': id})
    headers = {'Content-type': content_type,
               'User-Agent': 'OIMGridAPIClient/0.1 (OIM Grid API)'}
    conn = httplib.HTTPSConnection(host)
    try:
        conn.request('POST', returl, params, headers)
        response = conn.getresponse()
    except httplib.HTTPException, e:
        print 'Connection to %s failed: %s' % (newurl, e)
        raise httplib.HTTPException
    if not 'PENDING' in response.reason:
        if not 'OK' in response.reason:
            print response.status, response.reason
            sys.exit(1)
    data = response.read()
    conn.close()
    while 'PENDING' in data:
        conn.request('POST', returl, params, headers)
        try:
            response = conn.getresponse()
        except httplib.HTTPException, e:
            print 'Connection to %s failed: %s' % (newurl, e)
            raise httplib.HTTPException
        data = response.read()
        conn.close()
        if 'PENDING' in data:
            time.sleep(5)
            iterations = iterations + 1
            if iterations % 6 == 0:
                print 'Waiting for response from Certificate Authority. Please wait.'
                print ' Delay: ', float(iterations / 12), \
                ' minutes.'
            if iterations > 60:
                print "Maximum number of attempts reached. This script will now exit.\n Goc staff has been\nnotified of this issue."
                print  " You can open goc ticket to track this issue by going to https://ticket.grid.iu.edu\n"
                sys.exit(1)
        else:
            pass
    pkcs7raw = json.dumps(json.loads(data), sort_keys=True, indent=2)
    if 'FAILED' in data:
        print 'Fatal error: Certificate request has failed. Goc staff has been\nnotified of this issue.'
        print 'You can open goc ticket to track this issue by going to https://ticket.grid.iu.edu\n'
        sys.exit(1)

    # The slice and dice on the JSON output to get the certificate out
    # happens here - the problem is that the new lines are getting all screwy
    # in the output from OIM. We stringify the data, replace all the text
    # newline characters with actual new lines and the strip off the
    # extra data. There's probably a more efficient way to do this, but this
    # was the quick and dirty solution.
    #

    pkcs7raw = str(pkcs7raw)
    pkcs7raw = re.sub('\\\\n', '\n', pkcs7raw)
    pkcs7raw = pkcs7raw.partition('[')
    pkcs7raw = pkcs7raw[2]
    pkcs7raw = pkcs7raw.partition('"')
    pkcs7raw = pkcs7raw[2]
    pkcs7raw = pkcs7raw.split('"')
    i = 0
    cert_num = 0
    while cert_num < num_requests and i < len(pkcs7raw):
        certstring = str(pkcs7raw[i])
        if 'PKCS7' in certstring:
            write_certs(certstring, cert_num)
            cert_num = cert_num + 1
        i = i + 1
    print 'The number of requests made was ', num_requests
    print 'The number of certificates received is ', cert_num
    if cert_num != num_requests:
        sys.exit('Request and certifucate received mismatch')
    return


def create_certificate(line, count):
    print 'Generating certificate...'
    genprivate = createKeyPair(TYPE_RSA, 2048)
    keyname = line + '-' + str(count) + '-key.pem'

    # #### Writing private key####

    privkey = open(keyname, 'wb')
    key = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM,
            genprivate)
    privkey.write(key)
    privkey.close()

    new_csr = createCertRequest(genprivate, digest='sha1',
                                **config_items)
    csr = crypto.dump_certificate_request(crypto.FILETYPE_PEM, new_csr)
    csr = csr.replace('-----BEGIN CERTIFICATE REQUEST-----\n', ''
                      ).replace('-----END CERTIFICATE REQUEST-----\n',
                                '')
    csr = csr.replace('\n', '')
    return csr


if __name__ == '__main__':
    try:
        parse_args()
        def prompt_for_password(verify):

        # If verify == True, we are supposed to verify password.

            return getpass.getpass("Please enter the pass phrase for '%s':"
                                    % userprivkey)


        ssl_context = M2Crypto.SSL.Context('sslv3')
        ssl_context.load_cert_chain(usercert, userprivkey,
                                    callback=prompt_for_password)

        print 'Creating Certificate Directory (if necessary):', certdir
        try:
            os.makedirs(certdir)
        except OSError, exc:
            if exc.errno == errno.EEXIST:
                pass
            else:
                raise

        config_items = {'emailAddress': email}

    # ############################# Pipelining the bulk Certificate request process to send them at once##################################

        bulk_csr = list()
        count = 0
        num_requests = 0
        hosts = open(hostfile, 'rb')
        for line in hosts:
            count += 1
            line = line.rstrip('\n')
            config_items.update({'CN': line})  # ### New Config item list for every host#######
            print 'Beginning request process for', line
            csr = create_certificate(line, count)
            bulk_csr.append(csr)
            num_requests = num_requests + 1
            if count == 50:
                connect_request(ssl_context, bulk_csr)
                connect_approve(ssl_context)
                connect_retrieve()
                bulk_csr = ''
                count = 0

    # ####################################################################################################################################

        if count != 0 and count != 50:
            connect_request(ssl_context, bulk_csr)
            connect_approve(ssl_context)
            connect_retrieve()
        hosts.close()
    except Exception, e:
        print e
        sys.exit('''Uncaught Exception 
Please report the bug to goc@opensciencegrid.org. We would address your issue at the earliest.
'''
                 )
    except KeyboardInterrupt, k:
        print k
        sys.exit('''Interrupted by user\n''')
    sys.exit(0)
