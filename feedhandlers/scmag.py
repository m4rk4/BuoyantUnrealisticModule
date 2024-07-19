import json, re, pytz
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    slug = ''
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        if '/topic/' in path:
            path += '1'
        elif '/podcast-segment/' in path:
            slug = '?slug=' + paths[-1]
        elif '/cybercast/' in path:
            path = '/webcast' + path
            slug = '?learningType=cybercast&slug=' + paths[-1]
        else:
            path = '/editorial' + path
        path += '.json'

    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, slug)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def format_blocks(content_blocks):
    content_html = ''
    for block in content_blocks:
        if block['__typename'] == 'CoreParagraphBlock' or block['__typename'] == 'CoreHeadingBlock' or block['__typename'] == 'CoreListBlock' or block['__typename'] == 'CoreFreeformBlock':
            content_html += block['saveContent']
        elif block['__typename'] == 'CoreImageBlock':
            if block['attributes'].get('caption'):
                caption = re.sub(r'</?p>', '', block['attributes']['caption'])
            else:
                caption = ''
            content_html += utils.add_image(block['attributes']['url'], caption)
        elif block['__typename'] == 'CoreEmbedBlock':
            content_html += utils.add_embed(block['attributes']['url'])
        else:
            logger.warning('unhandled block type ' + block['__typename'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/debug.json')

    item = {}
    if next_data['pageProps'].get('content'):
        content_json = next_data['pageProps']['content']
        item['id'] = content_json['slug']
        item['url'] = url
        item['title'] = content_json['title']

        tz_loc = pytz.timezone('US/Eastern')
        dt_loc = datetime.fromisoformat(content_json['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        authors = []
        for it in content_json['authorCollection']['author']:
            authors.append(it['title'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        item['tags'] = []
        for key, val in content_json['editorialTaxonomy'].items():
            if isinstance(val, list):
                for it in val:
                    if it.get('name'):
                        item['tags'].append(it['name'])
        if not item['tags']:
            del item['tags']

        item['content_html'] = ''
        if content_json['editorialAdvanced'].get('featuredImage'):
            item['_image'] = content_json['editorialAdvanced']['featuredImage']['sourceUrl']
            if content_json['editorialAdvanced']['featuredImage'].get('caption'):
                caption = re.sub(r'</?p>', '', content_json['editorialAdvanced']['featuredImage']['caption'])
            else:
                caption = ''
            item['content_html'] += utils.add_image(item['_image'], caption)
        item['content_html'] += format_blocks(content_json['blocks'])

    elif next_data['pageProps'].get('meta'):
        meta_json = next_data['pageProps']['meta']
        item['id'] = meta_json['databaseId']
        item['url'] = meta_json['url']
        item['title'] = meta_json['title']

        # 2024-06-25T10:00:00.000America/New_York
        m = re.search(r'([\d-]+T[\d:\.]+)(.*)', meta_json['created'])
        if m:
            try:
                tz_loc = pytz.timezone(m.group(2))
            except:
                tz_loc = pytz.timezone('America/New_York')
            dt_loc = datetime.fromisoformat(m.group(1))
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        if meta_json.get('modified'):
            m = re.search(r'([\d-]+T[\d:\.]+)(.*)', meta_json['modified'])
            if m:
                try:
                    tz_loc = pytz.timezone(m.group(2))
                except:
                    tz_loc = pytz.timezone('America/New_York')
                dt_loc = datetime.fromisoformat(m.group(1))
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['date_modified'] = dt.isoformat()

        authors = []
        for it in meta_json['authors']:
            name = it['peopleAdvanced']['firstName'] + ' '
            if it['peopleAdvanced'].get('middleName'):
                name += it['peopleAdvanced']['middleName'] + ' '
            name += it['peopleAdvanced']['lastName']
            authors.append(name)
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        item['tags'] = []
        for key, val in meta_json['taxonomy'].items():
            item['tags'] += val.copy()

        if meta_json.get('jsonLdImages'):
            item['_image'] = meta_json['jsonLdImages'][0]

        if meta_json.get('description'):
            item['summary'] = meta_json['description']

        item['content_html'] = ''
        if meta_json['contentType'] == 'ppworksSegment' and next_data['pageProps'].get('segment'):
            segment_json = next_data['pageProps']['segment']
            if segment_json.get('blocks'):
                item['content_html'] += format_blocks(segment_json['blocks'])
            if segment_json['ppworksPodcastBasic'].get('youtubeId'):
                item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + segment_json['ppworksPodcastBasic']['youtubeId'])
            if segment_json['ppworksPodcastBasic'].get('libsynAudioId'):
                item['content_html'] += '<div>&nbsp;</div>' + utils.add_embed('https://play.libsyn.com/embed/episode/id/' + segment_json['ppworksPodcastBasic']['libsynAudioId'])

            for key, val in segment_json['ppworksSegmentAdvanced'].items():
                if key == 'guests' or key == 'hosts':
                    item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black; margin-bottom:0.5em;">{}</div>'.format(key.title())
                    for it in val:
                        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        if it['ppworksPeopleAdvanced'].get('ppworksHeadshot') and it['ppworksPeopleAdvanced']['ppworksHeadshot'].get('sourceUrl'):
                            item['content_html'] += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%" /></div>'.format(it['ppworksPeopleAdvanced']['ppworksHeadshot']['sourceUrl'])
                        item['content_html'] += '<div style="flex:3; min-width:128px;">'
                        name = it['peopleAdvanced']['firstName'] + ' '
                        if it['peopleAdvanced'].get('middleName'):
                            name += it['peopleAdvanced']['middleName'] + ' '
                        name += it['peopleAdvanced']['lastName']
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + name + '</div>'
                        name = ''
                        if it['ppworksPeopleAdvanced'].get('ppworksJobTitle') and it['ppworksPeopleAdvanced']['ppworksJobTitle'].get('name'):
                            name = it['ppworksPeopleAdvanced']['ppworksJobTitle']['name']
                        if it['ppworksPeopleAdvanced'].get('ppworksCompany') and it['ppworksPeopleAdvanced']['ppworksCompany'].get('companyProfileAdvanced'):
                            if name:
                                name += ' at '
                            name += it['ppworksPeopleAdvanced']['ppworksCompany']['companyProfileAdvanced']['companyName']
                        if name:
                            item['content_html'] += '<div>' + name + '</div>'
                        if it['ppworksPeopleAdvanced'].get('ppworksBio'):
                            item['content_html'] += it['ppworksPeopleAdvanced']['ppworksBio']
                        item['content_html'] += '</div></div>'

            if meta_json.get('additionalFields') and meta_json['additionalFields'].get('transcription'):
                item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black; margin-bottom:0.5em;">Transcript</div>'
                item['content_html'] += '<pre style="white-space:pre-wrap; ">' + meta_json['additionalFields']['transcription'] + '</pre>'

        elif meta_json['contentType'] == 'whitepaper' and next_data['pageProps'].get('whitepaper'):
            wp_json = next_data['pageProps']['whitepaper']
            if wp_json['whitepaperAdvanced'].get('featuredImage'):
                if wp_json['whitepaperAdvanced']['featuredImage'].get('caption'):
                    caption = re.sub(r'</?p>', '', wp_json['whitepaperAdvanced']['featuredImage']['caption'])
                else:
                    caption = ''
                item['content_html'] += utils.add_image(wp_json['whitepaperAdvanced']['featuredImage']['sourceUrl'], caption)

            if wp_json.get('content'):
                item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black; margin-bottom:0.5em;">Discussion Topics</div>'
                item['content_html'] += wp_json['content']

            if not item.get('author') and wp_json['whitepaperAdvanced'].get('companyProfile'):
                authors = []
                for it in wp_json['whitepaperAdvanced']['companyProfile']:
                    authors.append(it['companyProfileAdvanced']['companyName'])
                if authors:
                    item['author'] = {}
                    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        elif meta_json['contentType'] == 'learning':
            m = re.search(r'([\d-]+T[\d:\.]+)(.*)', meta_json['additionalFields']['startDate'])
            if m:
                try:
                    tz_loc = pytz.timezone(m.group(2))
                except:
                    tz_loc = pytz.timezone('America/New_York')
                dt_loc = datetime.fromisoformat(m.group(1))
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['content_html'] += '<h2>Live Webcast starts ' + utils.format_display_date(dt)
                m = re.search(r'([\d-]+T[\d:\.]+)(.*)', meta_json['additionalFields']['endDate'])
                if m:
                    try:
                        tz_loc = pytz.timezone(m.group(2))
                    except:
                        tz_loc = pytz.timezone('America/New_York')
                    dt_loc = datetime.fromisoformat(m.group(1))
                    delta = tz_loc.localize(dt_loc).astimezone(pytz.utc) - dt
                    item['content_html'] += ' (' + utils.calc_duration(delta.total_seconds()) + ')'
                item['content_html'] += '</h2>'

            if next_data['pageProps'].get('blocks'):
                item['content_html'] += format_blocks(next_data['pageProps']['blocks'])

            if next_data['pageProps']['learningAdvanced'].get('speakers'):
                item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black; margin-bottom:0.5em;">Speakers</div>'
                for speaker in next_data['pageProps']['learningAdvanced']['speakers']:
                    for it in speaker['speaker']:
                        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                        if it['peopleAdvanced'].get('headshot') and it['peopleAdvanced']['headshot'].get('sourceUrl'):
                            item['content_html'] += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%" /></div>'.format(it['peopleAdvanced']['headshot']['sourceUrl'])
                        item['content_html'] += '<div style="flex:3; min-width:128px;">'
                        name = it['peopleAdvanced']['firstName'] + ' '
                        if it['peopleAdvanced'].get('middleName'):
                            name += it['peopleAdvanced']['middleName'] + ' '
                        name += it['peopleAdvanced']['lastName']
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + name + '</div>'
                        name = ''
                        if it['peopleAdvanced'].get('companies'):
                            name = it['peopleAdvanced']['companies'][0]['jobTitle'] + ' at ' + it['peopleAdvanced']['companies'][0]['company'][0]['title']
                            item['content_html'] += '<div>' + name + '</div>'
                        if it['peopleAdvanced'].get('bio'):
                            item['content_html'] += it['peopleAdvanced']['bio']
                        item['content_html'] += '</div></div>'

            if not item.get('author') and next_data['pageProps']['learningAdvanced'].get('company'):
                authors = []
                for it in next_data['pageProps']['learningAdvanced']['company']:
                    authors.append(it['companyProfileAdvanced']['companyName'])
                if authors:
                    item['author'] = {}
                    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
