"""Check pharmacogenetics allele websites to see if anything has changed.
Send email notification if there is a change.
"""

import os
import sys
import re
import requests
import logging
import smtplib
import datetime
import glob
import argparse
import difflib
import ConfigParser
from bs4 import BeautifulSoup


def main():
    # get config file
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file_path', help='Path to configuration file')
    if len(sys.argv) != 2:
        parser.print_help()
        return 1
    args = parser.parse_args()
    try:
        params = read_in_config_file(args.config_file_path)
    except ConfigParser.Error as e:
        print 'Error reading in config file:'
        print e
        raise

    # set up logger
    logging.basicConfig(
        filename=params['log_path'], level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(filename)s - %(message)s'
    )
    logger = logging.getLogger()
    logger.info('---------------------------------------------------')
    logger.info('Starting %s.' % sys.argv[0])

    for i, site in enumerate(params['sites_to_check']):
        # get current webpage
        now = str(datetime.datetime.now())
        try:
            response = requests.get(site)
        except requests.ConnectionError:
            logger.error('Could not connect to webpage %s.' % site)
            send_email(
                params['email_sender'], params['email_password'],
                ['julie-wertz@uiowa.edu'],
                'PGX allele website script connection error', logger
            )
            continue
        page_html = response.text.encode('utf8')
        now_str = now[:now.rfind('.')].replace('-', '.')
        now_str = now_str.replace(':', '.').replace (' ', '_')

        # find most recent stored webpage file
        latest_page_version = None
        label = params['webpage_labels'][i]
        old_page_versions = glob.glob(
            '%s_*.html' % os.path.join(params['webpage_versions_dir'], label)
        )
        if old_page_versions:
            latest_page_version = os.path.join(
                params['webpage_versions_dir'], most_recent_file(
                    [os.path.basename(z) for z in old_page_versions]
                )
            )

        #check if webpage changed
        page_lines_curr = webpage_string_to_list(page_html)
        differences = None
        if latest_page_version:
            logger.info(
                'Webpage %s: latest version %s' %
                (site, latest_page_version)
            )
            with open(latest_page_version) as f:
                latest_page_str = f.read()
            page_lines_prev = webpage_string_to_list(latest_page_str)
            differences = [
                z for z in difflib.unified_diff(
                    page_lines_prev, page_lines_curr
                )
            ]
            if differences:
                logger.info(
                    'Webpage %s has changed.\nDifferences:\n%s' %
                    (site, '\n'.join(differences))
                )
            else:
                logger.info('No changes to webpage %s.' % site)
        else:
            logger.info(
                'No previous versions of webpage %s found.' % site
            )

        if (not latest_page_version) or differences:
            # copy of webpage
            archive_file_path_html = '%s_%s.html' % (
                os.path.join(params['webpage_versions_dir'], label), now_str
            )
            logger.info(
                'Creating copy of webpage %s. New filepath: %s' %
                (site, archive_file_path_html)
            )
            with open(archive_file_path_html, 'w') as f:
                f.write(page_html)

            # copy of text on webpage only
            archive_file_path_text = '%s_%s.txt' % (
                os.path.join(params['webpage_versions_dir'], label), now_str
            )
            logger.info(
                'Creating text copy of webpage %s. New filepath: %s' %
                (site, archive_file_path_text)
            )
            with open(archive_file_path_text, 'w') as f:
                f.write('\n'.join(page_lines_curr).encode('utf8'))

        if differences:
            email_message = (
                'Pharmacogenetics reference webpage %s has changed. '
                'Differences from previous version of webpage:\n%s\n\n'
                'This is an automated email. Contact julie-wertz@uiowa.edu '
                'for more info.' %
                (site, '\n'.join(differences))
            )
            send_email(
                params['email_sender'], params['email_password'],
                params['email_recipients'], email_message, logger
            )
    logger.info('%s complete.' % sys.argv[0])


def read_in_config_file(config_file_path):
    params = {}
    config = ConfigParser.ConfigParser()
    config.read(config_file_path)
    params['sites_to_check'] = [
        z.strip() for z in config.get('General', 'WebpagesToCheck').split(',')
    ]
    params['webpage_labels'] = [
        z.strip() for z in config.get('General', 'WebpageLabels').split(',')
    ]
    params['email_sender'] = config.get('General', 'EmailSender').strip()
    params['email_password'] = config.get('General', 'EmailPassword').strip()
    params['email_recipients'] = [
        z.strip() for z in config.get('General', 'EmailRecipients').split(',')
    ]
    params['webpage_versions_dir'] = config.get(
        'General', 'WebpageVersionsDir'
    ).strip()
    params['log_path'] = config.get('General', 'LogPath').strip()
    return params


def most_recent_file(file_list):
    """Returns most recently-created file in file_list. Assumes
    filename format [label]_year.month.day_hour.minute.second.[ext]
    """
    datetime_objs = {}
    for file_name in file_list:
        file_creation_datetime = file_name[
            file_name.find('_') + 1 : file_name.rfind('.')
        ]
        # year, month, day, hour, minute, second
        datetime_list = re.split('[_.]', file_creation_datetime)
        datetime_objs[
            datetime.datetime(*[int(x) for x in datetime_list])
        ] = file_name

    return datetime_objs[max(datetime_objs)]


def webpage_string_to_list(page_str):
    page_str = page_str[page_str.find('<body'):].strip()
    page_text = BeautifulSoup(page_str, 'html.parser').text
    return [x.strip() for x in page_text.split('\n') if x.strip()]


def send_email(sender, password, recipients, message, logger):
    try:
        server = smtplib.SMTP('smtp.gmail.com:587')
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        msg = '\r\n'.join([
            'From: %s' % sender, 'To: %s' % ','.join(recipients),
            'Subject: Change in allele reference webpage', '', message
        ])
        server.sendmail(sender, recipients, msg.encode('utf8'))
        server.quit()
        logger.info(
            'Successfully sent email. Recipients: %s' %', '.join(recipients)
        )
    except smtplib.SMTPException:
         logger.error(
            'Unable to send email. Sender: %s. Recipients: %s' %
            (sender, ', '.join(recipients))
        )


if __name__ == '__main__':
    sys.exit(main())

