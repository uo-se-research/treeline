import requests
import json
import logging
import configparser

logger = logging.getLogger("SlackMessages")

HOST="HostName"

"""
Login to the slack account and find the settings under "Incoming Webhooks". The POST URL should be in a 
credentials.ini file under a section named "DEFAULT".
    - go to https://api.slack.com/apps.
    - click on your app name or create  anew one.
    - navigate to "Incoming Webhooks".
    - copy the "Webhook URL" to the credentials.ini file with the key "SLACK".
"""
config = configparser.ConfigParser()
try:
    with open("credentials.ini") as configs:
        config.read_file(configs)
except IOError as e:
    logger.warning(f"No configuration file")
else:
    webhook_url = config['DEFAULT']['SLACK']


def post_message_to_slack(text: str):
    slack_data = {'text': f"*{HOST}:* {text}"}
    response = requests.post(webhook_url, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})

    if response.status_code != 200:
        logger.warning(f'Request to slack returned an error {response.status_code}, the response is:\n{response.text}')


"""
useful resources:
https://api.slack.com/messaging/sending
https://medium.com/arriendoasegurado/send-slack-messages-through-python-e6f7a1891bbd
https://slack.dev/python-slack-sdk/webhook/index.html
https://keestalkstech.com/2019/10/simple-python-code-to-send-message-to-slack-channel-without-packages/
"""