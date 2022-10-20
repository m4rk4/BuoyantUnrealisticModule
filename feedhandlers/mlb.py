import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_initial_state(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'window.initState = ({.*})\n', page_html)
    if not m:
        logger.warning('unable to find window.initialState in ' + url)
    return json.loads(m.group(1))


def get_content(url, args, save_debug=False):
    if '/news/' not in url:
        logger.warning('unhandled url ' + url)
        return None

    initial_state = get_initial_state(url)
    if not initial_state:
        return None
    if save_debug:
        utils.write_file(initial_state, './debug/debug.json')

    article_json = None
    for key, val in initial_state['apolloCache']['ROOT_QUERY'].items():
        if val['typename'] == 'StoryDetail':
            article_json = initial_state['apolloCache'][val['id']]
            break
    if not article_json:
        logger.warning('unable to find getForgeContentBySlug in ' + url)
        return None

    item = {}
    item['id'] = article_json['_translationId']
    item['url'] = url
    item['title'] = article_json['headline']

    def format_date(matchobj):
        return '.{}Z'.format(matchobj.group(1).zfill(3))
    date = re.sub(r'\.(\d+)Z', format_date, article_json['contentDate'])
    dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    date = re.sub(r'\.(\d+)Z', format_date, article_json['lastUpdatedDate'])
    dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('contributors'):
        authors = []
        for it in article_json['contributors']:
            authors.append(initial_state['apolloCache'][it['id']]['name'])
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    else:
        item['author']['name'] = 'MLB.com'

    item['tags'] = []
    for it in article_json['tags']:
        item['tags'].append(initial_state['apolloCache'][it['id']]['title'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('templateUrl'):
        item['_image'] = article_json['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')

    item['summary'] = article_json['summary']

    item['content_html'] = ''
    for it in article_json['parts']:
        part = initial_state['apolloCache'][it['id']]
        if part['type'] == 'markdown':
            content = markdown(part['content'].replace(' >', '>'))
            #content = '<p>{}</p>'.format(part['content'].replace('\n\n', '</p><p>').replace('\\', ''))
            soup = BeautifulSoup(content, 'html.parser')
            for el in soup.find_all('forge-entity'):
                new_html = ''
                if el['code'] == 'player':
                    new_html = '<a href="https://www.mlb.com/player/{}">{}</a>'.format(el['slug'].split('-')[-1], el.get_text())
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled forge-entity code {} in {}'.format(el['code'], item['url']))
            item['content_html'] += str(soup)

        elif part['type'] == 'photo':
            img_src = part['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')
            captions = []
            if part.get('contextualCaption'):
                captions.append(part['contextualCaption'])
            if part.get('credit'):
                captions.append(part['credit'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

        elif part['type'] == 'video':
            img_src = part['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')
            if part.get('description'):
                caption = part['description']
            elif part.get('title'):
                caption = part['title']
            else:
                caption = ''
            item['content_html'] += utils.add_video(part['mp4AvcPlayback'], 'video/mp4', img_src, caption)

        elif part['type'] == 'oembed':
            oembed = initial_state['apolloCache'][part['data']['id']]
            if oembed['providerName'] == 'Twitter':
                soup = BeautifulSoup(oembed['html'], 'html.parser')
                links = soup.find_all('a')
                item['content_html'] += utils.add_embed(links[-1]['href'])
            else:
                logger.warning('unhandled oembed provider {} in {}'.format(oembed['providerName'], item['url']))

        else:
            logger.warning('unhandled content part type {} in {}'.format(part['type'], item['url']))

    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
