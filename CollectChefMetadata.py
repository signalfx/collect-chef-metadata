from chef import autoconfigure, Node
from time import sleep
import logging
import sys
import getopt
import requests
import copy
import re
import pickle
import os
import argparse

DEFAULT_CONFIG_FILE = 'configuration.txt'
DEFAULT_LOG_FILE = '/tmp/ChefMetadata.log'
DEFAULT_SIGNALFX_REST_API = 'http://lab-api.corp.signalfuse.com:8080'
DEFAULT_PICKLE_FILE = 'pk_metadata.pk'
DEFAULT_SLEEP_DURATION = 60
DEFAULT_ENV_VARIABLE_NAME = 'SIGNALFX_API_TOKEN'
DEFAULT_LOG_HANDLER = 'logfile'

class Metadata(object):
    """
    Collect metadata of a chef node
    """

    def __init__(self,
            SIGNALFX_API_TOKEN,
            CONFIG_FILE,
            LOG_FILE,
            SIGNALFX_REST_API,
            PICKLE_FILE,
            SLEEP_DURATION,
            LOG_HANDLER
            ):
        self.api = autoconfigure()
        self.SIGNALFX_API_TOKEN = SIGNALFX_API_TOKEN
        self.CONFIG_FILE = CONFIG_FILE
        self.LOG_FILE = LOG_FILE
        self.SIGNALFX_REST_API = SIGNALFX_REST_API + '/v1/dimension'
        self.PICKLE_FILE = PICKLE_FILE
        self.SLEEP_DURATION = SLEEP_DURATION

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if LOG_HANDLER == 'logfile':
            self.handler = logging.FileHandler(DEFAULT_LOG_FILE)
        else:
            self.handler = logging.StreamHandler(sys.stdout)
        self.handler.setLevel(logging.INFO)
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.handler.setFormatter(self.formatter)
        self.logger.addHandler(self.handler)

        self.propertyNamePattern = re.compile('^[a-zA-Z_][a-zA-Z0-9_-]*$')
        self.config = []
        self.organization = ''
        self.nodes_metadata = []

    def run(self):
        """
        Read the configuration file
        Collect metadata from Chef Server API
        Send metadata to Signalfx
        Save the metadata for future comparisions
        """
        self.nodes_metadata = []
        self.readConfig()
        self.collectMetadataFromChef()
        for nodeInformation in self.nodes_metadata:
            self.sendMetadataToSignalfx(nodeInformation)
        self.saveMetadata()

    def saveMetadata(self):
        """
        Save the metadata as Python pickle
        """
        pickleData = {}
        for nodeInformation in self.nodes_metadata:
            pickleData[nodeInformation['chefUniqueId']] = nodeInformation
            pickleData[nodeInformation['chefUniqueId']].pop('chefUniqueId')
        output = open(self.PICKLE_FILE, 'wb')
        pickle.dump(pickleData, output)
        self.logger.info('Saved updated metadata to ' + self.PICKLE_FILE)
        output.close()

    def sendMetadataToSignalfx(self, nodeInformation):
        """
        Get ObjectID for the chefUniqueId dimension from Signalfx
        Check for changes between newly collected metadata and last run's data
        If there are any updates, send those changes to Signalfx
        """
        headers = {
            'X-SF-Token': self.SIGNALFX_API_TOKEN,
        }
        resp = self.getSignalfxObjectId(nodeInformation, headers)
        if len(resp.json()['rs']) == 0:
            self.logger.info('Signalfx does not have an object '
                             + 'for your dimension chefUniqueId:'
                             + nodeInformation['chefUniqueId'])
            return
        signalfxObjectId = resp.json()['rs'][0]
        self.logger.info("ObjectID for " + nodeInformation['chefUniqueId']
                         + " is " + signalfxObjectId)
        new_metadata = self.checkForUpdatesInMetadata(
            copy.deepcopy(nodeInformation))
        if new_metadata:
            resp = requests.patch(
                self.SIGNALFX_REST_API + '/' + signalfxObjectId,
                params=new_metadata, headers=headers)
        else:
            self.logger.info('No new metadata is found for ' +
                             nodeInformation['chefUniqueId'])

    def checkForUpdatesInMetadata(self, current_data):
        """
        Read the data saved in the last run
        Compare it with the current metadata and pop unchanged items

        return: updated metadata
        """
        inputPickle = open(self.PICKLE_FILE, 'rb')
        self.logger.info('Reading previous metadata from ' + self.PICKLE_FILE)
        savedMetadata = pickle.load(inputPickle)
        inputPickle.close()
        if current_data['chefUniqueId'] not in savedMetadata:
            return current_data
        previous_data = savedMetadata[current_data['chefUniqueId']]
        for key in previous_data.keys():
            if key in current_data and current_data[key] == previous_data[key]:
                current_data.pop(key)
        current_data.pop('chefUniqueId')
        return current_data

    def getSignalfxObjectId(self, nodeInformation, headers):
        """
        Get ObjectID for the chefUniqueId dimension from Signalfx

        return: the api response
        """
        params = {
            'query': 'chefUniqueId:' + nodeInformation['chefUniqueId'],
            'getIDs': 'true'
        }
        resp = requests.get(self.SIGNALFX_REST_API, params=params, headers=headers)
        if resp.status_code != 200:
            self.logger.error('Unable to get ID of' +
                              'chefUniqueId object from Signalfx')
            print(resp.raise_for_status())
            self.exitNow()
        return resp

    def readConfig(self):
        """
        Read the configuration file
        """
        self.config = []
        with open(self.CONFIG_FILE, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if not line.startswith("#") and line != '\n':
                    attribute = line.rstrip('\n')
                    if self.checkPropertyNameSyntax(attribute
                                                    .replace('.', '_')):
                        self.config.append(attribute)

    def checkPropertyNameSyntax(self, attribute):
        """
        Check if the attribute name from the configuration file
        follows the pattern expected by Signalfx

        return: True or False
        """
        if not self.propertyNamePattern.match(attribute):
            self.logger.error('Invalid attribute name '
                              + attribute
                              + '. Attribute names should follow '
                              + 'the regex pattern ^[a-zA-Z_][a-zA-Z0-9_-]*$')
            return False
        return True

    def exitNow(self):
        """
        Exit from the program with a message on the console
        """
        print("Error Occured: logged into "+DEFAULT_LOG_FILE+"! Exiting...")
        sys.exit(1)

    def apiGetRequest(self, endpoint):
        """
        Execute the Chef Server api's GET request for given endpoint
        """
        value = None
        try:
            value = self.api.api_request('GET', endpoint)
        except Exception:
            self.logger.error(
                'Unable to perform api GET request', exc_info=True)
            self.exitNow()
        return value

    def collectMetadataFromChef(self):
        """
        Get the current organization name and its nodes
        Get the metadata for each node
        """
        organization_details = self.apiGetRequest('')
        self.organization = organization_details['name']
        nodes = self.apiGetRequest('/nodes')
        for node_name in nodes.keys():
            self.getNodeInformation(node_name)

    def getNodeInformation(self, node_name):
        """
        Get node attributes(metadata) using Node.attributes of PyChef
        Store the values of the attributes selected by the user for each node
        """
        chefUniqueId = self.organization + "_" + node_name
        node_details = Node(node_name)
        nodeInformation = {}
        nodeInformation['chefUniqueId'] = chefUniqueId
        nodeInformation['chef_environment'] = node_details.chef_environment
        for attribute in self.config:
            attributeValue = self.getAttributeValue(
                attribute, node_details)
            if attributeValue:
                attribute = self.adjustAttributeName(attribute)
                nodeInformation[attribute] = attributeValue
        self.nodes_metadata.append(nodeInformation)

    def adjustAttributeName(self, attribute):
        """
        Replace '.' by '_' in the attributes listed in the configuration file
        and return it
        """
        attribute = attribute.replace('.', '_')
        if not attribute.startswith('chef_'):
            attribute = 'chef_' + attribute
        return attribute

    def getAttributeValue(self, attribute, node_details):
        """
        Return the value of the given attribute
        """
        tokens = attribute.split('.')
        tempValue = node_details
        for token in tokens:
            try:
                tempValue = tempValue[token]
            except Exception:
                self.logger.error('Invalid attribute '+attribute+' is listed in '
                                  + self.CONFIG_FILE, exc_info=True)
                return None
        if isinstance(tempValue, dict):
            self.logger.error('Attribute value for ' +
                              attribute + ' cannot be a dictionary!')
            return None
        if isinstance(tempValue, list) and not (
                any(isinstance(x, dict) for x in tempValue)):
            return '$'.join(tempValue)
        return str(tempValue)

def getArgumentParser():
    """
    Create a parser object

    return: argparse.ArgumentParser() object
    """
    parser = argparse.ArgumentParser(description='Collects the metadata '+
        'about Chef nodes and forwards it to SignalFx.', add_help=True)

    parser.add_argument('--env-variable-name', action='store',
                    dest='ENV_VARIABLE_NAME',
                    default=DEFAULT_ENV_VARIABLE_NAME,
                    help='Set SIGNALFX_API_TOKEN with your SIGNALFX_API_TOKEN as value '+
                    'in your environment variables. '+
                    'You can change the environment variable name to look for, '+
                    'using this option.'+
                    'Default is '+DEFAULT_ENV_VARIABLE_NAME, type=str)
    parser.add_argument('--config-file', action='store',
                    dest='CONFIG_FILE',
                    default=DEFAULT_CONFIG_FILE,
                    help='File with the list of attributes to be attached to '+
                    '\'ChefUniqueId\' on SignalFx. '+
                    'Default is '+DEFAULT_CONFIG_FILE, type=str)
    parser.add_argument('--log-file', action='store',
                    dest='LOG_FILE',
                    default=DEFAULT_LOG_FILE,
                    help='Log file to store the messages. '+
                    'Default is '+DEFAULT_LOG_FILE, type=str)
    parser.add_argument('--log-to', action='store',
                    dest='LOG_HANDLER',
                    default=DEFAULT_LOG_HANDLER,
                    choices=('stdout', 'logfile'),
                    help='Choose between \'stdout\' and \'logfile\''+
                    'to redirect log messages. '+
                    'Use --log-file to change the default log file location'+
                    'Default to this option is '+DEFAULT_LOG_HANDLER, type=str)
    parser.add_argument('--signalfx-rest-api', action='store',
                    dest='SIGNALFX_REST_API',
                    default=DEFAULT_SIGNALFX_REST_API,
                    help='SignalFx REST API endpoint. '+
                    'Default is '+DEFAULT_SIGNALFX_REST_API, type=str)
    parser.add_argument('--pickle-file', action='store',
                    dest='PICKLE_FILE',
                    default=DEFAULT_PICKLE_FILE,
                    help='Pickle file to store the last retrieved metadata. '+
                    'Default is '+DEFAULT_PICKLE_FILE, type=str)
    parser.add_argument('--sleep-duration', action='store',
                    dest='SLEEP_DURATION',
                    default=DEFAULT_SLEEP_DURATION,
                    help='Specify the sleep duration. Default is 60'+
                    'Default is '+str(DEFAULT_SLEEP_DURATION), type=int)
    parser.add_argument('--use-cron', action="store_true", 
                    default=False,
                    help='use this option if you want to run the program '+
                    'using Cron. Default is False, meaning that program will '+
                    'use sleep(SLEEP_DURATION) instead of cron')

    return parser
    

def main(argv):
    """
    Parse command line arguments and start the program.
    """
    parser = getArgumentParser()
    
    user_args = vars(parser.parse_args(argv))

    # Get the SIGNALFX_API_TOKEN from environment variables
    try:
        SIGNALFX_API_TOKEN = os.environ[user_args['ENV_VARIABLE_NAME']]
    except Exception as e:
        print("Error: Unable to find a variable with the name \""+
            user_args['ENV_VARIABLE_NAME']+"\" in your environment")
        print("For help, look for --env-variable-name option in the guide\n")
        parser.print_help()
        sys.exit(2)

    user_args.pop('ENV_VARIABLE_NAME')
    user_args['SIGNALFX_API_TOKEN'] = SIGNALFX_API_TOKEN
    use_cron = user_args.pop('use_cron', False)
    
    m = Metadata(**user_args)
    if use_cron:
        m.run()
    else:
        while True:
            m.run()
            sleep(m.SLEEP_DURATION)

if __name__ == "__main__":
    main(sys.argv[1:])
