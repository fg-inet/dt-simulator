""" Parse .har files and generate transfers objects for the data transfer simulator """

import json
import sys
import datetime
import logging
from simulator.transfer import Transfer


__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logging.getLogger("harParser")

class HarParser(object):
	def __init__(self, fh, transferManager, verification=False):
		self.transferManager = transferManager
		self.verification = verification
		self.harData = json.load(fh)
		self.harWebObjects = self.harData['log']['entries']
		self.origin = None


	def _retrieveContentLength(self, webObject):
		try:
			contentLength = int([ int(x['value']) for x in webObject['response']['headers'] if x['name'] == 'Content-Length'][0])
			# functional variant is too ugly: 
			# for x in filter ( lambda t : t[0] == "Content-Length", map( lambda h: (h['name'],h['value']) , webObject['response']['headers']) ): (_, contentLength) = x
			return contentLength

		except (IndexError, KeyError):
			return 0


	def _retrieveBodySize(self, webObject):
		bodySize = int(webObject['response']['bodySize'])
		return bodySize if bodySize > 0 else 0


	def generateTransfer(self, harStartTimeObj, webObject):

		# all relative times in ms, but python parses daytime objects 
		startTimeStr = webObject['startedDateTime']
		startTimeObj = datetime.datetime.strptime(startTimeStr[:-6], "%Y-%m-%dT%H:%M:%S.%f")
		startTime    = (startTimeObj - harStartTimeObj).total_seconds() * 1000
		assert startTime >= 0

		requestTime  = webObject['time']
		finishTime   = startTime + requestTime

		requestUrl   = webObject['request']['url']
		origin       = requestUrl.split("/")[2]
		ssl          = requestUrl.startswith("https")
		
		headerSize   = int(webObject['response']['headersSize'])
		size 		 = 0

		# update size from either bodySize (verification=True) or Content-Length (verification=False) if possible
		bodySize      = self._retrieveBodySize(webObject)
		contentLength = self._retrieveContentLength(webObject)

		if self.verification:
			size = bodySize if bodySize > 0 else contentLength
		else:
			size = contentLength if contentLength > 0 else bodySize
		size += headerSize


		#logger.debug("{st} {rt:>4d} {size:>9d} {ssl:<3} {origin}".format(st=startTime, rt=requestTime, size=size, ssl="ssl" if ssl else "", origin=origin))
		
		if size < 1:
			logger.warning("read broken transfer {st} {rt:>4d} {size:>9d} {ssl:<3} {origin}".format(st=startTime, rt=requestTime, size=size, ssl="ssl" if ssl else "", origin=origin))
			transfer = None
		else:
			objectTimings = {'connect': webObject['timings']['connect']/1000, 
							 'receive': webObject['timings']['receive']/1000, 
							 'wait': webObject['timings']['wait']/1000, 
							 'blocked': webObject['timings']['blocked']/1000,
							 'dns': webObject['timings']['dns']/1000, 
							 'send': webObject['timings']['send']/1000}

			transfer = Transfer(size, origin, ssl, startTime/1000, finishTime/1000, objectTimings)
		
		return transfer



	def generateTransfers(self):

		harStartTimeStr = self.harWebObjects[0]['startedDateTime']
		harStartTimeObj = datetime.datetime.strptime(harStartTimeStr[:-6], "%Y-%m-%dT%H:%M:%S.%f")

		# read all transfers
		transfers = sorted(filter(lambda t: t, map(lambda o: self.generateTransfer(harStartTimeObj, o), self.harWebObjects)), key=lambda t: t.harStartTime)

		# parse url and 
		self.origin = transfers[0].origin

		# add first transfer to transfer manager and enable
		self.transferManager.addTransfer(transfers[0])
		self.transferManager.enableTransfer(transfers[0])
		
		# add transfers and generate dependencies
		finishingTransfers = sorted(transfers, key=lambda t: t.harFinishTime)
		lastDependency = None
		nextDependency = finishingTransfers.pop(0)
		for transfer in transfers[1:]:

			self.transferManager.addTransfer(transfer)

			# can we move dependency chain forward?
			while nextDependency and nextDependency.harFinishTime < transfer.harStartTime:
				lastDependency = nextDependency
				nextDependency = finishingTransfers.pop(0)

			assert not nextDependency or nextDependency.harFinishTime >= transfer.harStartTime

			# no one has finished yet
			if lastDependency == None:
				logger.warning("harfile has multiple first transfers - index file missing?")
				self.transferManager.enableTransfer(transfer)
			else:
				#logger.debug("adding child: {0} to transfer: {1}".format(transfer.getInfo(), lastDependency.getInfo()))
				lastDependency.addChild(transfer)
