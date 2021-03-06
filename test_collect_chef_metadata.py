import unittest
import collect_chef_metadata
import os


class Test_collect_chef_metadata(unittest.TestCase):

    def test_argument_parser_for_default_parameters(self):
        """
        Check if the parser is correctly setting the default parameters
        """
        os.environ['SIGNALFX_API_TOKEN'] = 'abcdefghijk'
        argv = []
        parser = collect_chef_metadata.get_argument_parser()
        args = vars(parser.parse_args(argv))
        self.assertNotEqual(args, None)
        self.assertEqual(args['CONFIG_FILE'],
                         collect_chef_metadata.DEFAULT_CONFIG_FILE)
        self.assertEqual(args['LOG_FILE'],
                         collect_chef_metadata.DEFAULT_LOG_FILE)
        self.assertEqual(args['SIGNALFX_REST_API'],
                         collect_chef_metadata.DEFAULT_SIGNALFX_REST_API)
        self.assertEqual(args['PICKLE_FILE'],
                         collect_chef_metadata.DEFAULT_PICKLE_FILE)
        self.assertEqual(args['SLEEP_DURATION'],
                         collect_chef_metadata.DEFAULT_SLEEP_DURATION)
        self.assertEqual(args['ENV_VARIABLE_NAME'],
                         collect_chef_metadata.DEFAULT_ENV_VARIABLE_NAME)
        self.assertEqual(args['LOG_HANDLER'],
                         collect_chef_metadata.DEFAULT_LOG_HANDLER)

    def test_argument_parser_for_custom_parameters(self):
        """
        Check if the parser is correctly setting the user specified parameters
        """
        os.environ['MY_SIGNALFX_API_TOKEN'] = 'abcdefghijk'
        # simulate user arguments as a list
        custom_argv = ['--config-file', 'my_configuration.txt',
                       '--log-file', '/tmp/dummy_log_file',
                       '--signalfx-rest-api',
                       'http://lab-api.corp.signalfuse.com:8080',
                       '--pickle-file', 'my_pk_metadata.pk',
                       '--sleep-duration', '10',
                       '--env-variable-name', 'MY_SIGNALFX_API_TOKEN',
                       '--log-handler', 'stdout'
                       ]
        parser = collect_chef_metadata.get_argument_parser()
        args = vars(parser.parse_args(custom_argv))
        self.assertNotEqual(args, None)
        self.assertEqual(args['CONFIG_FILE'], 'my_configuration.txt')
        self.assertEqual(args['LOG_FILE'], '/tmp/dummy_log_file')
        self.assertEqual(args['SIGNALFX_REST_API'],
                         'http://lab-api.corp.signalfuse.com:8080')
        self.assertEqual(args['PICKLE_FILE'], 'my_pk_metadata.pk')
        self.assertEqual(args['SLEEP_DURATION'], 10)
        self.assertEqual(args['ENV_VARIABLE_NAME'], 'MY_SIGNALFX_API_TOKEN')
        self.assertEqual(args['LOG_HANDLER'], 'stdout')

    def test_check_property_name_syntax(self):
        """
        Check if the attribute values follow the expected pattern by SignalFx
        """
        m = collect_chef_metadata.ChefMetadata(
            SIGNALFX_API_TOKEN='dummy_signalfx_api_token',
            LOG_HANDLER='stdout')
        self.assertTrue(m.check_property_name_syntax("language_python"), True)
        self.assertTrue(
            m.check_property_name_syntax("language_python3_version"), True)
        self.assertTrue(
            m.check_property_name_syntax("language_python3-version"), True)

        self.assertFalse(
            m.check_property_name_syntax("language.python"), False)
        self.assertFalse(
            m.check_property_name_syntax("9chef_environment"), False)

    def test_adjust_attribute_name(self):
        """
        Check if the '.' in attributes listed in configuration.txt are replaced
        by '_'.

        Check if 'chef_' is being added to the attribute names
        """
        m = collect_chef_metadata.ChefMetadata(
            SIGNALFX_API_TOKEN='dummy_signalfx_api_token',
            LOG_HANDLER='stdout')
        self.assertEqual(
            m.adjust_attribute_name('language.python'), 'chef_language_python')
        self.assertEqual(
            m.adjust_attribute_name('chef_environment'), 'chef_environment')

    def test_get_attribute_value(self):
        """
        Check if the attribute value is retrieved as expected and as a string
        Check if attribute value is a list, then the list elements are joined
        by '$'.
        Check if attribute value is a dictionary, then None is returned.
        """
        m = collect_chef_metadata.ChefMetadata(
            SIGNALFX_API_TOKEN='dummy_signalfx_api_token',
            LOG_HANDLER='stdout')
        self.assertEqual(
            m.get_attribute_value('languages.python.version', {'languages':
                                                               {'python':
                                                                {'version':
                                                                 '2.7.8'
                                                                 }
                                                                }
                                                               }), '2.7.8')
        self.assertEqual(
            m.get_attribute_value('roles', {'roles':
                                            ['web server',
                                             'web cache']
                                            }), 'web server$web cache')
        self.assertEqual(
            m.get_attribute_value('languages.python', {'languages':
                                                       {'python':
                                                        {'version': '2.7.8'
                                                         }
                                                        }
                                                       }), None)


if __name__ == '__main__':
    unittest.main()
