import pytz
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    api_url = 'https://www.dailykos.com/api/v1/story_content/' + paths[4]
    story_json = utils.get_url_json(api_url)
    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['story_id']
    item['url'] = 'https://www.dailykos.com' + story_json['story_url']
    item['title'] = story_json['story_text']['title']

    soup = BeautifulSoup(story_json['story_text']['formatted_date_and_time'], 'html.parser')
    date = ''
    for el in soup.find_all(class_='timestamp'):
        if 'story__date--short' not in el['class']:
            date += el.get_text().strip() + ' '
    if el.get('data-time-zone'):
        date += el['data-time-zone']
    try:
        # print(date)
        dt = dateutil.parser.parse(date.strip()).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    except:
        logger.warning('unhandled date {}in {}'.format(date, item['url']))

    if story_json['story_text'].get('update_time'):
        # TODO: is timezone seems to be local?
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(story_json['story_text']['update_time'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()

    item['author'] = {
        "name": story_json['author']['byline']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = [x['name'] for x in story_json['tags']]

    item['content_html'] = ''

    if story_json['story_text'].get('primary_image'):
        soup = BeautifulSoup(story_json['story_text']['primary_image'], 'html.parser')
        item['image'] = soup.img['src']
        if soup.figcaption and soup.figcaption.get_text().strip():
            caption = soup.figcaption.decode_contents()
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['image'], caption)

    story_text = ''
    if story_json['story_text'].get('story_text_before_ad'):
        story_text += story_json['story_text']['story_text_before_ad']
    if story_json['story_text'].get('story_text_after_ad'):
        story_text += story_json['story_text']['story_text_after_ad']

    if story_text:
        soup = BeautifulSoup(story_text, 'html.parser')
        for el in soup.find_all('figure', class_='image-captioned'):
            if el.figcaption and el.figcaption.get_text().strip():
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            new_html = utils.add_image(el.img['src'], caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in soup.find_all('blockquote', class_=False):
            el['style'] = 'border-left:3px solid light-dark(#ccc, #333); margin:1.5em 10px; padding:0.5em 10px;'

        # Set recursive=False to prevent recursive embeds
        for el in soup.find_all(class_='dk-editor-embed', recursive=False):
            # print(str(el))
            new_html = ''
            if el.find(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            else:
                it = el.find(class_='iframe_placeholder')
                if it:
                    if it.get('href') and it['href'] != '#':
                        new_html = utils.add_embed(it['href'])
                    elif it.get('data-src'):
                        new_html = utils.add_embed(it['data-src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled dk-editor-embed in ' + item['url'])

        for el in soup.find_all(class_='story-intro-divider'):
            el.attrs = {}
            el.name = 'hr'
            el['style'] = "width:80%; margin:2em auto 2em auto;"

        for el in soup.find_all(class_='dk-action-link'):
            el.decompose()

        item['content_html'] += str(soup)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'feeds.dailykos.com':
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'tags':
        api_url = 'https://www.dailykos.com/api/v1/tags/{}/everything?page=1'.format(paths[1])
        feed_title = paths[1] + ' News at Daily Kos'
    elif paths[0] == 'users':
        api_url = 'https://www.dailykos.com/api/v1/users/{}/everything?page=1'.format(paths[1])
        feed_title = unquote_plus(paths[1]).title() + ' News at Daily Kos'
    elif paths[0] == 'history' and paths[1] == 'list':
        api_url = 'https://www.dailykos.com/api/v1/history/lists/{}?offset=0&sort_by=time&sort_direction=desc'.format(paths[2])
        feed_title = unquote_plus(paths[1]).title() + ' News at Daily Kos'
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    if isinstance(api_json, list):
        stories = api_json[:10]
    else:
        stories = api_json['results']

    n = 0
    feed_items = []
    for story in stories:
        if story.get('url'):
            story_url = 'https://' + split_url.netloc + story['url']
        elif story.get('full_path'):
            story_url = 'https://' + split_url.netloc + story['full_path']
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
