"""
Yum plugin for Amazon S3 access.

This plugin provides access to a protected Amazon S3 bucket using either boto
or Amazon's REST authentication scheme.

On CentOS this file goes into /usr/lib/yum-plugins/s3.py

You will also need two configuration files.   See s3.conf and s3test.repo for
examples on how to deploy those.


"""

#   Copyright 2011, Robert Mela
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.



SECRET_KEY = 'my_amazon_secret_key'
KEY_ID = 'my_amazon_key_id'

def createBotoGrabber():
	import boto
	from urlparse import urlparse
	import sys

	class BotoGrabber:
		def __init__(self, awsAccessKey, awsSecretKey, baseurl):
			print "BotoGrabber init BASE_URL=%s" % baseurl
			if not baseurl: raise Exception("BotoGrabberInit got blank baseurl")
			try: baseurl = baseurl[0]
			except: pass
			self.s3 = boto.connect_s3(awsAccessKey, awsSecretKey)
			self.baseurl = urlparse(baseurl)
			self.bucket_name = self.baseurl.netloc.split('.')[0]
			self.key_prefix = self.baseurl.path[1:]

		def _key_name(self,url):
			return "%s%s" % ( self.key_prefix, url )

		def _key(self, key_name):
			bucket = self.s3.get_bucket(self.bucket_name)
			return bucket.get_key(key_name)

		def urlgrab(self, url, filename=None, **kwargs):
			"""urlgrab(url) copy the file to the local filesystem"""
			print "BotoGrabber urlgrab url=%s filename=%s" % ( url, filename )
			key_name = self._key_name(url)
			print "BotoGrabber urlgrab url=%s key_name=%s filename=%s" % ( url, key_name, filename )
			key = self._key(key_name)
			if not key: raise Exception("Can not get key for key=%s" % key_name )
			if not filename: filename = key.key
			key.get_contents_to_filename(filename)
			return filename
			# zzz - does this return a value or something?
	
		def urlopen(self, url, **kwargs):
			"""urlopen(url) open the remote file and return a file object"""
			print "BotoGrabber urlopen url=%s" % url 
			return self._key(url)

		def urlread(self, url, limit=None, **kwargs):
			"""urlread(url) return the contents of the file as a string"""
			print "BotoGrabber urlread url=%s" % url 
			return self._key(url).read()

	return BotoGrabber



def createUrllibGrabber():

	import os
	import sys
	import urllib2
	import time, hashlib, hmac, base64

	class UrllibGrabber:
		@classmethod
		def s3sign(cls,request, secret_key, key_id, date=None):
        		date=time.strftime("%a, %d %b %Y %H:%M:%S +0000", date or time.gmtime() )
        		host = request.get_host()
        		bucket = host.split('.')[0]
        		request.add_header( 'Date', date)
        		resource = "/%s%s" % ( bucket, request.get_selector() )
        		sigstring = """%(method)s\n\n\n%(date)s\n%(canon_amzn_resource)s""" % {
			                               'method':request.get_method(),
			                               #'content_md5':'',
			                               #'content_type':'', # only for PUT
			                               'date':request.headers.get('Date'),
			                               #'canon_amzn_headers':'',
			                               'canon_amzn_resource':resource }
        		digest = hmac.new(secret_key, sigstring, hashlib.sha1 ).digest()
        		digest = base64.b64encode(digest)
        		request.add_header('Authorization', "AWS %s:%s" % ( key_id,  digest ))

		def __init__(self, awsAccessKey, awsSecretKey, baseurl ):
			try: baseurl = baseurl[0]
			except: pass
			self.baseurl = baseurl
			self.awsAccessKey = awsAccessKey
			self.awsSecretKey = awsSecretKey

		def _request(self,url):
			req = urllib2.Request("%s%s" % (self.baseurl, url))
			UrllibGrabber.s3sign(req, self.awsSecretKey, self.awsAccessKey )
			return req

		def urlgrab(self, url, filename=None, **kwargs):
			"""urlgrab(url) copy the file to the local filesystem"""
			print "UrlLibGrabber urlgrab url=%s filename=%s" % ( url, filename )
			req = self._request(url)
			if not filename:
				filename = req.get_selector()
				if filename[0] == '/': filename = filename[1:]
			out = open(filename, 'w+')
			resp = urllib2.urlopen(req)
			buff = resp.read(8192)
			while buff:
				out.write(buff)
				buff = resp.read(8192)
			return filename
			# zzz - does this return a value or something?
	
		def urlopen(self, url, **kwargs):
			"""urlopen(url) open the remote file and return a file object"""
			return urllib2.urlopen( self._request(url) )

		def urlread(self, url, limit=None, **kwargs):
			"""urlread(url) return the contents of the file as a string"""
			return urllib2.urlopen( self._request(url) ).read()

	return UrllibGrabber


def createGrabber():
	try:
		rv = createBotoGrabber()
		print "Created BotoGrabber"
		return rv
	except:
		print "Creating UrllibGrabber"
		return createUrllibGrabber()

AmazonS3Grabber = createGrabber()

import os
import sys
import urllib
from yum.plugins import TYPE_CORE
from yum.yumRepo import YumRepository
from yum import config

import yum.Errors

__revision__ = "1.0.0"

requires_api_version = '2.5'
plugin_type = TYPE_CORE
CONDUIT=None

def config_hook(conduit):
	config.RepoConf.s3_enabled = config.BoolOption(False)

def init_hook(conduit):
	""" 
	Plugin initialization hook. Setup the S3 repositories.
	"""

	repos = conduit.getRepos()
	for key,repo in repos.repos.iteritems():
		print type(repo)
		print "s3_enabled=%s" % repo.s3_enabled
		if isinstance(repo, YumRepository) and repo.s3_enabled: 
			new_repo = AmazonS3Repo(key)
			new_repo.baseurl = repo.baseurl
			new_repo.mirrorlist = repo.mirrorlist
			new_repo.basecachedir = repo.basecachedir
			new_repo.gpgcheck = repo.gpgcheck
			new_repo.proxy = repo.proxy
			new_repo.enablegroups = repo.enablegroups
			del repos.repos[repo.id]
			repos.add(new_repo)
			#repos.add(new_repo)


class AmazonS3Repo(YumRepository):
	"""
	Repository object for Amazon S3.
	"""
	
	def __init__(self, repoid):
		YumRepository.__init__(self, repoid)
		self.enable()
		self.grabber = None

	def setupGrab(self):
		YumRepository.setupGrab(self)
		self.grabber = AmazonS3Grabber(KEY_ID, SECRET_KEY )

	def _getgrabfunc(self): raise Exception("get grabfunc!")
	def _getgrab(self):
		if not self.grabber:
			self.grabber = AmazonS3Grabber(KEY_ID, SECRET_KEY, baseurl=self.baseurl )
		return self.grabber

	grabfunc = property(lambda self: self._getgrabfunc())
	grab = property(lambda self: self._getgrab())

