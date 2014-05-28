#!/usr/bin/env python
__author__ = 'sameer'

# First steps towards a CGI script that will take in a user's details, generate
# a sputnik profile, create a key, and request a CSR

from OpenSSL.crypto import PKey, X509Req
from OpenSSL import crypto
import cgi, cgitb
from jinja2 import Environment, FileSystemLoader
import random, string

class ProcessException(Exception):
    pass

import traceback, sys

def generate_key():
    key_len = 4096
    key_type = crypto.TYPE_RSA

    key = PKey()
    key.generate_key(key_type, key_len)
    return key

def generate_csr(pkey, name):
    req = X509Req()
    req.set_pubkey(pkey)
    subject = req.get_subject()

    for key, value in name.iteritems():
        setattr(subject, key, value)

    req.sign(pkey, "md5")
    return req

if __name__ == "__main__":
    cgitb.enable()
    form = cgi.FieldStorage()
    jinja_env = Environment(loader=FileSystemLoader("../templates"))

    try:
        # Create a profile.ini and initdb.sh
        profile = {}
        db = {}
        for field in form.keys():
            if field.startswith("profile_"):
                profile[field[8:]] = form.getvalue(field)
            if field.startswith("db_"):
                db[field[3:]] = form.getvalue(field)

        if 'domain' not in profile:
            raise ProcessException("'domain' not set")

        profile['dbpassword'] = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        profile_template = jinja_env.get_template('profile.ini')
        profile_text = profile_template.render(**profile)
        with open("%s.profile" % profile['domain'], "a") as profile_file:
            profile_file.write(profile_text)

        db_template = jinja_env.get_template('initdb.sh')
        db_text = db_template.render(**db)
        with open("%s.dbinit" % profile['domain'], "a") as db_file:
            db_file.write(db_text)

        # Create a key and CSR
        pkey = generate_key()

        name = {}
        for key in ['C', 'ST', 'L', 'O', 'OU', 'CN', 'emailAddress']:
            value = form.getvalue('csr_%s' % key)
            if value is not None:
                name[key] = value

        if 'CN' not in name:
            raise ProcessException("CN missing")

        if name['CN'] != profile['domain']:
            raise ProcessException("CN doesn't match domain")

        csr = generate_csr(pkey, name)
        csr_pem = crypto.dump_certificate_request(crypto.FILETYPE_PEM, csr)

        # Dump the key to a file
        pkey_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey)
        with open("%s.key" % name['CN'], "a") as key_file:
            key_file.write(pkey_pem)

        # Give the request to the user
        html_template = jinja_env.get_template('request_success.html')
        html = html_template.render(csr=csr_pem)
    except ProcessException as e:
        html_template = jinja_env.get_template('request_failure.html')
        html = html_template.render(error=e, traceback=[])
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        html_template = jinja_env.get_template('request_failure.html')
        html = html_template.render(error=e, traceback=traceback.format_tb(exc_traceback))

    print "Content-Type: text/html"
    print
    print html

