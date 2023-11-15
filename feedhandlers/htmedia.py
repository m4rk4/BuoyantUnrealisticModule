import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    m = re.search(r'-(\d+)\.html', split_url.path)
    if not m:
        logger.warning('unhandled url with no id ' + url)
        return None

    api_url = 'https://api.hindustantimes.com/api/articles/' + m.group(1)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['metadata']['url'])
    item['title'] = api_json['headline']

    dt = datetime.fromisoformat(api_json['firstPublishedDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['lastModifiedDate']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if api_json['metadata'].get('authorsList'):
        for it in api_json['metadata']['authorsList']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif api_json['metadata'].get('agency'):
        item['author']['name'] = api_json['metadata']['agency']
    authors = []
    if api_json['metadata'].get('editedByList'):
        for it in api_json['metadata']['editedByList']:
            authors.append(it['name'])
        if item['author'].get('name'):
            item['author']['name'] += ' | Edited by ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            item['author']['name'] = 'Edited by ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if api_json['metadata'].get('affKeywordsSet'):
        item['tags'] = []
        if api_json['metadata']['affKeywordsSet'].get('parent_keyword'):
            item['tags'].append(api_json['metadata']['affKeywordsSet']['parent_keyword'])
        if api_json['metadata']['affKeywordsSet'].get('child_keywords'):
            item['tags'] += api_json['metadata']['affKeywordsSet']['child_keywords']
        if not item['tags']:
            del item['tags']

    item['content_html'] = ''
    if api_json['type'] == 'video':
        item['content_html'] += utils.add_embed(api_json['leadMedia']['video']['embedUrl'])
        if api_json.get('summary'):
            item['summary'] = api_json['summary']
            item['content_html'] += '<p>{}</p>'.format(api_json['summary'])
        return item

    if api_json.get('summary'):
        item['summary'] = api_json['summary']
        item['content_html'] += '<p><em>{}</em></p>'.format(api_json['summary'])

    if api_json.get('leadMedia'):
        if api_json['leadMedia'].get('video'):
            if api_json['leadMedia']['video'].get('embedUrl'):
                item['content_html'] += utils.add_embed(api_json['leadMedia']['video']['embedUrl'])
            else:
                logger.warning('unhandled leadMedia video in ' + item['url'])
        elif api_json['leadMedia'].get('image'):
            item['_image'] = api_json['leadMedia']['image']['images']['ampImage']
            if not (api_json.get('listElement') and api_json['listElement'][0]['type'] == 'slide'):
                captions = []
                if api_json['leadMedia']['image'].get('caption'):
                    captions.append(api_json['leadMedia']['image']['caption'])
                if api_json['leadMedia']['image'].get('imageCredit'):
                    captions.append(api_json['leadMedia']['image']['imageCredit'])
                item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if api_json.get('introBody'):
        item['content_html'] += api_json['introBody']

    gallery = None
    slide_no = 0
    for element in api_json['listElement']:
        if element['type'] == 'paragraph':
            body = re.sub(r'<h2>also read.+?</h2>', '', element['paragraph']['body'], flags=re.I)
            #body = re.sub(r'<strong>also read.+?</h2>', '', element['paragraph']['body'], flags=re.I)
            item['content_html'] += body
        elif element['type'] == 'image':
            captions = []
            if element['image'].get('caption'):
                captions.append(element['image']['caption'])
            if element['image'].get('imageCredit'):
                captions.append(element['image']['imageCredit'])
            item['content_html'] += utils.add_image(element['image']['images']['original'], ' | '.join(captions))
        elif element['type'] == 'video':
            if element['video'].get('embedUrl'):
                item['content_html'] += utils.add_embed(element['video']['embedUrl'])
        elif element['type'] == 'embed':
            soup = BeautifulSoup(element['embed']['body'], 'html.parser')
            if soup.find(class_='twitter-tweet'):
                links = soup.find_all('a')
                item['content_html'] += utils.add_embed(links[-1]['href'])
            elif soup.find(class_='instagram-media'):
                item['content_html'] += utils.add_embed(soup.blockquote['data-instgrm-permalink'])
            elif soup.find(class_='reddit-embed-bq'):
                links = soup.find_all('a')
                item['content_html'] += utils.add_embed(links[0]['href'])
            elif soup.iframe:
                item['content_html'] += utils.add_embed(soup.iframe['src'])
            elif element['embed']['body'].startswith('<img'):
                item['content_html'] += utils.add_image(soup.img['src'])
            else:
                logger.warning('unhandled element embed in ' + item['url'])
        elif element['type'] == 'slide':
            if element.get('video') and element['video'].get('url'):
                if '.mp4' in element['video']['url']:
                    item['content_html'] += utils.add_video(element['video']['url'], 'video/mp4')
                else:
                    item['content_html'] += utils.add_video(element['video']['url'], 'application/x-mpegURL')
            elif element.get('image'):
                # TODO: parse photo credits from the content
                item['content_html'] += utils.add_image(element['image']['images']['original'], element['image'].get('imageCredit'))
            else:
                logger.warning('unhandled slide {} in {}'.format(element['id'], item['url']))
            if not gallery:
                page_html = utils.get_url_html(item['url'])
                soup = BeautifulSoup(page_html, 'lxml')
                for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
                    ld_json = json.loads(el.string)
                    if ld_json.get('@type') and ld_json['@type'] == 'MediaGallery':
                        gallery = ld_json['mainEntityOfPage']['associatedMedia']
                        break
                if not gallery:
                    logger.warning('unable to find ld+json MediaGallery in ' + item['url'])
            if gallery:
                if gallery[slide_no].get('name'):
                    item['content_html'] += '<p>{}</p>'.format(gallery[slide_no]['name'])
            item['content_html'] += '<div>&nbsp;</div>'
            slide_no += 1
        elif element['type'] == 'liveblog':
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            dt = datetime.fromisoformat(element['firstPublishedDate']).astimezone(timezone.utc)
            item['content_html'] += '<div>Update: {}</div>'.format(utils.format_display_date(dt))
            if element.get('createdBy'):
                item['content_html'] += '<div>By {}</div>'.format(element['createdBy'])
            if element.get('title'):
                item['content_html'] += '<h3>{}</h3>'.format(re.sub(r'^<p>(.*?)</p>$', r'\1', element['title']))
            item['content_html'] += element['liveBlog']['body']
        else:
            logger.warning('unhandled element type {} in {}'.format(element['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.hindustantimes.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
