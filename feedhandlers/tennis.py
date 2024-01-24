import re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_photo(photo):
    captions = []
    if photo.get('title'):
        captions.append(photo['title'])
    elif photo['image'].get('title'):
        captions.append(photo['image']['title'])
    if photo.get('fields') and photo['fields'].get('copyright'):
        captions.append(photo['fields']['copyright'])
    img_src = photo['image']['templateUrl'].replace('{formatInstructions}', 'w_1200,c_thumb,g_auto,q_auto,f_jpg')
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if 'articles' in paths:
        story_url = 'https://dapi.tennis.com/v2/content/en-us/stories/' + paths[-1]
        story_json = utils.get_url_json(story_url)
    elif 'videos' in paths:
        story_url = 'https://dapi.tennis.com/v2/content/en-us/videos/' + paths[-1]
        story_json = utils.get_url_json(story_url)

    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['_entityId']
    item['url'] = url
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['contentDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['lastUpdatedDate'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": story_json['createdBy']}

    if story_json.get('tags'):
        item['tags'] = []
        for it in story_json['tags']:
            if it.get('externalSourceName') and it['externalSourceName'] != 'notifications':
                item['tags'].append(it['title'])

    if story_json.get('thumbnail'):
        item['_image'] = story_json['thumbnail']['thumbnailUrl']

    if story_json.get('summary'):
        item['summary'] = story_json['summary']

    item['content_html'] = ''
    if story_json.get('headline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(story_json['headline'])

    if story_json['type'] == 'story':
        for part in story_json['parts']:
            if part['type'] == 'markdown':
                m = re.search(r'^>\s?(.*?)\*\*\*(.*?)\*\*\*$', part['content'])
                if m:
                    item['content_html'] += utils.add_pullquote(m.group(1), m.group(2))
                else:
                    item['content_html'] += markdown(part['content'])
            elif part['type'] == 'photo':
                item['content_html'] += add_photo(part)
            elif part['type'] == 'album':
                album = utils.get_url_json(part['selfUrl'])
                if album:
                    for it in album['elements']:
                        if it['type'] == 'photo':
                            item['content_html'] += add_photo(it)
                        else:
                            logger.warning('unhandled album element type {} in {}'.format(it['type'], item['url']))
            elif part['type'] == 'customentity':
                if part['entityCode'] == 'video':
                    item['content_html'] += utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(part['fields']['videoId']))
                elif part['entityCode'] == 'promo':
                    pass
                else:
                    logger.warning('unhandled custom entity code {} in {}'.format(part['entityCode'], item['url']))
            elif part['type'] == 'external' and part['externalType'] == 'oembed':
                item['content_html'] += utils.add_embed(part['inputUrl'])
            else:
                logger.warning('unhandled story part type {} in {}'.format(part['type'], item['url']))
    elif story_json['type'] == 'customentity' and story_json['entityCode'] == 'video':
        item['content_html'] += utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(story_json['fields']['videoId']))
    else:
        logger.warning('unhandled content type {} in {}'.format(story_json['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    stories = []
    if 'baseline' in paths or 'reporters' in paths or 'tags' in paths:
        api_url = 'https://www.tennis.com/api/lazy/load?data=%7B%22Name%22:%22EditorialListLoadMoreModule%22,%22Module%22:%7B%22Count%22:10,%22Skip%22:0,%22Type%22:%22stories%22,%22Tags%22:[%22{}%22]%7D%7D'.format(paths[-1])
        print(api_url)
        page_html = utils.get_url_html(api_url)
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            for el in soup.find_all('a', class_='-story'):
                story = {}
                story['slug'] = el['href']
                stories.append(story)
    else:
        api_json = utils.get_url_json('https://dapi.tennis.com/v2/content/en-us/stories')
        if api_json:
            stories = api_json['items']

    if save_debug:
        utils.write_file(stories, './debug/feed.json')

    n = 0
    items = []
    for story in stories:
        if story['slug'].startswith('/'):
            story_url = 'https://www.tennis.com' + story['slug']
        else:
            if next((it for it in story['tags'] if it.get('externalSourceName') == 'baselines'), None):
                story_url = 'https://www.tennis.com/baseline/articles/' + story['slug']
            else:
                story_url = 'https://www.tennis.com/news/articles/' + story['slug']
        if save_debug:
            logger.debug('getting contents for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
