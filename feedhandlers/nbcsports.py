import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_video_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    el = soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['id'] = el['content']
        item['url'] = el['content']

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:description"})
    if el:
        item['summary'] = el['content']

    el = soup.find('link', attrs={"type": "application/smil+xml"})
    if el:
        item['_video'] = utils.get_redirect_url(el['href'])
        if re.search(r'\.mp4', item['_video'], flags=re.I):
            video_type = 'video/mp4'
        else:
            video_type = 'application/x-mpegURL'

    if not item.get('_video'):
        return None

    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    item['content_html'] = utils.add_video(item['_video'], video_type, item['_image'], caption)
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'vplayer' in paths or split_url.netloc == 'vplayer.nbcsports.com':
        return get_video_content(url, args, site_json, save_debug)

    drupal_html = utils.get_url_html(utils.clean_url(url) + '?_wrapper_format=drupal_ajax')
    if not drupal_html:
        return None
    if save_debug:
        utils.write_file(drupal_html, './debug/debug.html')

    drupal_ajax = json.loads(re.sub(r'^<textarea>(.*)</textarea>$', r'\1', drupal_html))
    if save_debug:
        utils.write_file(drupal_ajax, './debug/debug.json')

    soup = None
    content = None
    for it in drupal_ajax:
        if it.get('command') and it['command'] == 'insert':
            soup = BeautifulSoup(it['data'], 'html.parser')
            content = soup.find(class_=['content', 'field--name-body'])
            if content:
                break
    if not content:
        return None

    item = {}
    item['id'] = url
    item['url'] = url

    el = soup.find(attrs={"data-publish-date": True})
    if el:
        tz_loc = pytz.timezone('US/Eastern')
        dt_loc = datetime.fromtimestamp(int(el['data-publish-date']))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    el = soup.find(class_='field--name-field-short-title')
    if el:
        item['title'] = el.get_text()

    el = soup.find(class_='authored-box')
    if el:
        item['author'] = {"name": re.sub(r'^\W*By ', '', el.get_text().strip(), flags=re.I)}

    item['tags'] = []
    item['tags'].append(paths[0])
    item['tags'].append(paths[1].replace('-', ' '))

    item['content_html'] = ''

    el = soup.find(class_='article-header-video')
    if el:
        it = el.find(attrs={"data-mpx-src": True})
        if it:
            item['content_html'] += utils.add_embed(it['data-mpx-src'])

    el = soup.find(class_='field--name-field-hero-image')
    if el:
        it = el.find(attrs={"srcset": True})
        if it:
            item['_image'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, utils.image_from_srcset(it['srcset'], 1200))
            if not item.get('content_html'):
                item['content_html'] += utils.add_image(item['_image'])

    if content:
        for el in content.find_all(class_='embed-link'):
            new_html = ''
            if 'embed-tw' in el['class']:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif el.iframe:
                if el.iframe.get('data-src'):
                    new_html = utils.add_embed(el.iframe['data-src'])
                elif el.iframe.get('src'):
                    new_html = utils.add_embed(el.iframe['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled embed-link in ' + item['url'])

        for el in content.find_all(class_='embedded-entity'):
            new_html = ''
            it = el.find(attrs={"data-mpx-src": True})
            if it:
                new_html = utils.add_embed(it['data-mpx-src'])
            elif el.find(class_='embed__image'):
                img = el.find('img')
                if img:
                    if img.get('data-src'):
                        img_src = '{}:{}{}'.format(split_url.scheme, split_url.netloc, img['data-src'])
                    else:
                        img_src = '{}:{}{}'.format(split_url.scheme, split_url.netloc, img['src'])
                    captions = []
                    it = el.find(class_='field--name-field-caption')
                    if it:
                        captions.append(it.get_text())
                    it = el.find(class_='field--name-field-credit')
                    if it:
                        captions.append(it.get_text())
                    new_html = utils.add_image(img_src, ' | '.join(captions))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled embedded-entity in ' + item['url'])

        for el in content.find_all(class_=['article-promo', 'cdw-related-content', 'disqus_thread', 'rsn-mps-slot', 'share-buttons-h', 'Subtopics']):
            el.decompose()

        for el in content.find_all(id='disqus_thread'):
            el.decompose()

        item['content_html'] += content.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', attrs={"data-drupal-selector": "drupal-settings-json"})
    if not el:
        logger.warning('unable to find drupal settings in ' + url)
        return None

    drupal_json = json.loads(el.string)
    if save_debug:
        utils.write_file(drupal_json, './debug/drupal.json')

    team_id = ''
    for key, val in drupal_json['rsn']:
        if val == paths[0]:
            team_id = key
            break

    if not team_id:
        logger.warning('unknown team id in ' + url)
        return None



    if paths[0] == 'bayarea':
        teams = {
            "49ers": "https://www.nbcsports.com/rsn-api/team/recent-posts/127",
            "athletics": "https://www.nbcsports.com/rsn-api/team/recent-posts/131",
            "giants": "https://www.nbcsports.com/rsn-api/team/recent-posts/76",
            "kings": "https://www.nbcsports.com/rsn-api/team/recent-posts/92",
            "Sharks": "https://www.nbcsports.com/rsn-api/team/recent-posts/58",
            "warriors": "https://www.nbcsports.com/rsn-api/team/recent-posts/91",
            "headstrong": "https://www.nbcsports.com/rsn-api/recent/653911?page=0",
            "race-in-america": "https://www.nbcsports.com/rsn-api/recent/28906?page=0",
        }
    elif paths[0] == 'boston':
        teams = {
            "bruins": "https://www.nbcsports.com/rsn-api/team/recent-posts/44",
            "celtics": "https://www.nbcsports.com/rsn-api/team/recent-posts/133",
            "new-england-revolution": "https://www.nbcsports.com/rsn-api/recent/9856?page=0",
            "patriots": "https://www.nbcsports.com/rsn-api/team/recent-posts/28",
            "red-sox": "https://www.nbcsports.com/rsn-api/team/recent-posts/66",
            "camera-guys": "https://www.nbcsports.com/rsn-api/recent/336196?page=0",
            "fantasy-football": "https://www.nbcsports.com/rsn-api/recent/22221?page=0",
            "simulation-station": "https://www.nbcsports.com/rsn-api/recent/345761?page=0"
        }
    elif paths[0] == 'chicago':
        teams = {
            "bears": "https://www.nbcsports.com/rsn-api/team/recent-posts/27",
            "blackhawks": "https://www.nbcsports.com/rsn-api/team/recent-posts/46",
            "bulls": "https://www.nbcsports.com/rsn-api/team/recent-posts/101",
            "cubs": "https://www.nbcsports.com/rsn-api/team/recent-posts/75",
            "white-sox": "https://www.nbcsports.com/rsn-api/team/recent-posts/117",
            "fire": "https://www.nbcsports.com/rsn-api/recent/23696?page=0",
            "loyola-ramblers": "https://www.nbcsports.com/rsn-api/recent/649926?page=0",
            "ncaa": "https://www.nbcsports.com/rsn-api/recent/20831?page=0",
            "red-stars": "https://www.nbcsports.com/rsn-api/recent/23686?page=0",
            "sky": "https://www.nbcsports.com/rsn-api/recent/23671?page=0"
        }
    else:
        return None

    n = 0
    feed_items = []
    for key, val in teams.items():
        if len(paths) > 1 and key != paths[1]:
            continue
        api_json = utils.get_url_json(val)
        if api_json:
            if isinstance(api_json['data'], list):
                recent_posts = api_json['data']
            elif isinstance(api_json['data'], dict):
                recent_posts = api_json['data']['most_recent']
            for post in recent_posts:
                post_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post['path'])
                if save_debug:
                    logger.debug('getting content for ' + post_url)
                item = get_content(post_url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break

    feed = utils.init_jsonfeed(args)
    feed['title'] = 'NBCSports ' + paths[0].title()
    if len(paths) > 1:
        feed['title'] = paths[1].replace('-', ' ').title() + ' | ' + feed['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed