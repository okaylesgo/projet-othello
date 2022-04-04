import socket
from jsonNetwork import Timeout, sendJSON, receiveJSON, NotAJSONObject, fetch
from threading import Thread, Timer
import importlib
import sys
from championship import Championship, addPlayer, getAllPlayers, getState, changePlayerStatus, updateState, hookRegister, addMatchResult
from graphics import ui
import json
import argparse

def checkClient(address):
	'''
		Ping client
	'''
	print('checking client {}:'.format(address), end=' ')
	try:
		response = fetch(address, {
			'request': 'ping'
		})
		if response['response'] == 'pong':
			status = 'online'
		else:
			raise ValueError()
	except:
		status = 'lost'

	print(status)
	return status

def checkAllClient():
	for client in getAllPlayers(getState()):
		status = checkClient(client['address'])
		updateState(changePlayerStatus(client['address'], status))


def finalizeSubscription(address):
	'''
		Add client if successfully pinged
	'''
	status = checkClient(address)
	if status == 'online':
		updateState(changePlayerStatus(address, 'online'))

def preSubscription(name, address, matricules, points=0, badMoves=0, matchCount=0):
	updateState(addPlayer(name, address, matricules, points, badMoves, matchCount))


def startSubscription(client, address, request):
	'''
	Because client may be single threaded, he may start listening to request
	after sending his substriction. We wait for 1 second before pinging him
	'''
	clientAddress = (address[0], int(request['port']))
	
	print('Subscription received for {} with address {}'.format(request['name'], clientAddress))

	if any([not isinstance(matricule, str) for matricule in request['matricules']]):
		raise TypeError("Matricules must be strings")

	if clientAddress not in getState()['players']:
		preSubscription(request['name'], clientAddress, request['matricules'])
	
	sendJSON(client, {
		'response': 'ok'
	})

	Timer(1, finalizeSubscription, [clientAddress]).start()


def processRequest(client, address):
	'''
		Route request to request handlers
	'''
	print('request from', address)
	try:
		request = receiveJSON(client)
		
		if request['request'] == 'subscribe':
			startSubscription(client, address, request)
		else:
			raise ValueError('Unknown request \'{}\''.format(request['request']))

	except Timeout:
		sendJSON(client, {
			'response': 'error',
			'error': 'transmition take too long'
		})
	except NotAJSONObject as e:
		sendJSON(client, {
			'response': 'error',
			'error': str(e)
		})
	except KeyError as e:
		sendJSON(client, {
			'response': 'error',
			'error': 'Missing key {}'.format(str(e))
		})
	except Exception as e:
		sendJSON(client, {
			'response': 'error',
			'error': str(e)
		})


def listenForRequests(port):
	'''
		Start thread to listen to requests.
		Returns a function to stop the thread.
	'''
	running = True
	def processClients():
		with socket.socket() as s:
			s.bind(('0.0.0.0', port))
			s.settimeout(1)
			s.listen()
			print('Listen to', port)
			while running:
				try:
					client, address = s.accept()
					with client:
						processRequest(client, address)
				except socket.timeout:
					pass
	
	listenThread = Thread(target=processClients, daemon=True)
	listenThread.start()

	def stop():
		nonlocal running
		running = False
		listenThread.join()

	return stop

def formatClient(client):
	return '{}: {}'.format(client['name'], client['points'])

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('gameName', help='The name of the game')
	parser.add_argument('-p', '--port', help='The port the server use to listen for subscription', default=3000)
	parser.add_argument('-l', '--load', help='the JSON file of a previous championship that you want to resume')
	parser.add_argument('-c', '--count', help='the number of match you want to play', default=float('inf'), type=int)
	args = parser.parse_args()

	gameName = args.gameName
	port = args.port
	load = args.load

	count = args.count
	if load is not None:
		with open(load, encoding='utf8') as file:
			content = json.load(file)

		for player in content['players']:
			preSubscription(
				player['name'],
				tuple(player['address']),
				player['matricules'],
				player['points'],
				player['badMoves'],
				player['matchCount']
			)

		for match in content['results']:
			updateState(addMatchResult(
				tuple((tuple(elem) for elem in match['players'])),
				match['winner'],
				match['badMoves'],
				match['moveCount'],
				match['playerTimes'],
				match['totalTime']
			))

	stopSubscriptions = listenForRequests(port)

	Game = importlib.import_module('games.{}.game'.format(gameName)).Game
	render = importlib.import_module('games.{}.render'.format(gameName)).render

	hookRegister('matchEnd', checkAllClient)

	stopChampionship = Championship(Game, count)

	ui(gameName, render)

	stopSubscriptions()
	stopChampionship()
