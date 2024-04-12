import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        if not split_url.query:
            path = '/index.json'
        else:
            params = parse_qs(split_url.query)
            if params.get('id'):
                path = '/single/{0}.json?slug={0}'.format(params['id'][0])
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'
        if paths[0] == 'single':
            path += '?slug=' + paths[1]
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
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


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    entry_json = next_data['pageProps']['entry']

    item = {}
    item['id'] = entry_json['id']
    item['url'] = 'https://www.web3isgoinggreat.com/single/' + entry_json['readableId']
    item['title'] = entry_json['title']

    # Only YYYY-MM-DD format
    dt = datetime.fromisoformat(entry_json['date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {"name": "Molly White"}

    item['tags'] = []
    if entry_json.get('collection'):
        item['tags'] += entry_json['collection'].copy()
    if entry_json.get('filters'):
        for key, val in entry_json['filters'].items():
            item['tags'] += val.copy()
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if entry_json.get('image'):
        if entry_json['image']['isLogo']:
            item['_image'] = 'https://primary-cdn.web3isgoinggreat.com/entryImages/logos/resized/{}_300.webp'.format(entry_json['image']['src'])
            caption = ''
        else:
            item['_image'] = 'https://primary-cdn.web3isgoinggreat.com/entryImages/resized/{}_500.webp'.format(entry_json['image']['src'])
            caption = entry_json['image'].get('caption')
        if 'on-dark' in entry_json['image']['class']:
            item['content_html'] += utils.add_image(item['_image'], caption, img_style='background:#333;')
        else:
            item['content_html'] += utils.add_image(item['_image'], caption)

    item['content_html'] += re.sub(r'^(.*?)<p>', r'<p>\1</p>', entry_json['body'])

    glossary_entries = next_data['pageProps']['glossary']['entries']
    glossary = ''
    def replace_buttons(matchobj):
        nonlocal glossary_entries
        nonlocal glossary
        m = re.search(r'id="([^"]+)"', matchobj.group(1))
        if m and glossary_entries.get(m.group(1)):
            key = m.group(1)
            glossary += '<dl><dt style="font-weight:bold;">{}</dt><dd style="font-size:0.9em;">{}</dd></dl>'.format(glossary_entries[key]['term'], glossary_entries[key]['definition'])
        return '<b><u>' + matchobj.group(2) + '</u></b>'
    item['content_html'] = re.sub(r'<button([^>]+)>([^<]+)</button>', replace_buttons, item['content_html'])

    if entry_json.get('links'):
        item['content_html'] += '<h3>Links:</h3><ul>'
        for link in entry_json['links']:
            item['content_html'] += '<li><a href="{}">{}</a>'.format(link['href'], link['linkText'])
            if link.get('extraText'):
                item['content_html'] += link['extraText']
            try:
                link_item = utils.get_content(link['href'], {"embed": True})
                if link_item:
                    item['content_html'] += '<div>&nbsp;</div>' + link_item['content_html'] + '<div>&nbsp;</div>'
                    if link.get('archiveTweetPath') and not link_item.get('url'):
                        # Use archive if tweet that was deleted/removed
                        item['content_html'] += '<div>Archived tweet:</div>'
                        item['content_html'] += utils.add_image('https://tweet-archives-cdn.web3isgoinggreat.com/{}/screenshot.webp'.format(link['archiveTweetPath']))
                        if link.get('archiveTweetAssets'):
                            for key, val in link['archiveTweetAssets'].items():
                                if val.get('images'):
                                    for i in range(val['images']):
                                        caption = '<div style="text-align:center;">Tweet #{}, image #{}</div>'.format(int(key) + 1, i + 1)
                                        item['content_html'] += utils.add_image('https://tweet-archives-cdn.web3isgoinggreat.com/{}/assets/{}-{}.webp'.format(link['archiveTweetPath'], key, i), heading=caption)
                                        item['content_html'] += '<div>&nbsp;</div>'
            except:
                logger.warning('exception getting content for ' + link['href'])
                pass
            item['content_html'] += '</li>'
        item['content_html'] += '</ul>'

    if glossary:
        item['content_html'] += '<h3>Glossery</h3>' + glossary
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
