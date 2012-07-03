#!/usr/bin/python

# $Id: RetrieveCert.py 14967 2012-06-08 00:42:56Z jeremy $

import urllib
import httplib
import sys
import ConfigParser
import argparse
import json
import time
import re
import os

"""

This script retrieves the PKCS7 certificate from the server once it has been
approved and issued. No authentication is required.

 Usage: RetrieveCert.py [options]

 Options:
  -h, --help                    Show this help message and exit
  -i ID, --id=ID                Request ID# of certificate request
  -q, --quiet                   Don't print status messages to stdout
"""


# Set up Option Parser
#
parser = argparse.ArgumentParser()
parser.add_argument("-i",  "--id",
                    action="store", dest="id", required = True,
                    help="Specify ID# of certificate to retrieve",
                    metavar="ID")
parser.add_argument("-f",  "--first", action="store", dest="first", default="y",
                    help="Is this the first retrieval of the certificate? (y or n)",
                    metavar="FIRST")
parser.add_argument("-q",  "--quiet",
                    action="store_false", dest="verbose", default=True,
                    help="don't print status messages to stdout")
args = parser.parse_args()

#print "Parsing variables..."
id = args.id
first = args.first

#
# Read from the ini file
#
Config = ConfigParser.ConfigParser()
Config.read("OSGTools.ini")
host = Config.get("OIMData", "host")
requrl = Config.get("OIMData", "returl")

content_type = Config.get("OIMData", "content_type")

# Some vars for file operations
filetype = "pkcs7-cert"
fileext = "pem"
filename = "%s.%s.%s" % (filetype,id,fileext)

# Build the connection to the web server - the request header, the parameters
# needed and then pass them into the server
#
# The data returned is in JSON format so to make it a little more human
# readable we pass it through the json module to pretty print it
#
# A WHILE loop exists to keep trying to retrieve the certificate if there
# is a delay in issuing
#
# Then we use a regexp to fix the munged up new lines that get returned
# and put the cert into the proper format, clipping of the extraneous
# JSON formatting and write the certificate file out
#
def connect():
    iterations = 1
    print "\nConnecting to server..."
    params = urllib.urlencode({
	'host_request_id': id,
	     })
    headers = {
        'Content-type': content_type,
	'User-Agent': 'OIMGridAPIClient/0.1 (OIM Grid API)'
        }
    conn = httplib.HTTPConnection(host)
    conn.request("POST", requrl, params, headers)
    response = conn.getresponse()
    if not "OK" in response.reason:
       print response.status, response.reason
    data = response.read()
    conn.close()

    while "PENDING" in data:
	conn.request("POST", requrl, params, headers)
	response = conn.getresponse()
	data = response.read()
	conn.close()
	print json.dumps(json.loads(data), sort_keys = True, indent = 2)
	print "\nWaiting for response from Certificate Authority. Please wait."
	time.sleep(30)
	iterations = iterations + 1
	print "Attempt:", iterations, " Delay: ", iterations/2, " minutes."
    if not "OK" in response.reason:
       print response.status, response.reason
    #
    # The slice and dice on the JSON output to get the certificate out
    # happens here - the problem is that the new lines are getting all screwy
    # in the output from OIM. We stringify the data, replace all the text
    # newline characters with actual new lines and the strip off the
    # extra data. There's probably a more efficient way to do this, but this
    # was the quick and dirty solution.
    #
    pkcs7raw = json.dumps(json.loads(data), sort_keys = True, indent = 2)
    pkcs7raw = str(pkcs7raw)
    pkcs7raw = re.sub('\\\\n', '\n', pkcs7raw)
    pkcs7raw = pkcs7raw.partition('[')
    pkcs7raw = pkcs7raw[2]
    pkcs7raw = pkcs7raw.partition('\"')
    pkcs7raw = pkcs7raw[2]
    pkcs7raw = pkcs7raw.partition('\"')
    pkcs7raw = pkcs7raw[0]
    certfile = open(filename, 'w+')
    certfile.write(pkcs7raw)
    certfile.close
    print "\nCertificate written to ", filename, "\n"


if __name__ == '__main__':
	if first == "y":
	    print "\nOn first retrieval of certificate, a one minute delay is required.\nPlease be patient.\n"
	    time.sleep(60)
	connect()
	sys.exit(0)
