import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    if '/xxxxx-video/' in url or '/xxxxx-podcast/' in url:
        media_src = ''
        el = soup.find('script', string=re.compile('mediaID'))
        if el:
            i = el.string.find('[')
            j = el.string.rfind(']') + 1
            data_json = json.loads(el.string[i:j])

            item['id'] = data_json[0]['content']['media'][0]['mediaID']
            item['title'] = data_json[0]['content']['media'][0]['title']
            media_src = data_json[0]['content']['media'][0]['source']

            tz_loc = pytz.timezone('US/Eastern')
            dt_loc = datetime.fromtimestamp(data_json[0]['content']['contentInfo']['publishedAt'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

            item['authors'] = [{"name": x} for x in data_json[0]['content']['contentInfo']['author']]
            if len(item['authors']) > 0:
                item['author'] = {
                    "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(data_json[0]['content']['contentInfo']['author']))
                }

            if data_json[0]['content']['contentInfo'].get('keywords'):
                item['tags'] = [it.strip() for it in data_json[0]['content']['contentInfo']['keywords'].split(',')]
        else:
            item['id'] = urlsplit(url).path

            el = soup.find('meta', attrs={"property": "og:title"})
            if el:
                item['title'] = el['content']

            el = soup.find(attrs={"itemprop": "uploadDate"})
            if el:
                tz_loc = pytz.timezone('US/Eastern')
                dt_loc = datetime.fromisoformat(el['content'])
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt)

            item['authors'] = []
            for el in soup.find_all('meta', attrs={"name": "author"}):
                item['authors'].append({"name": el['content']})
            if len(item['authors']) > 0:
                item['author'] = {
                    "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
                }

            el = soup.find('meta', attrs={"name": "keywords"})
            if el and el['content']:
                item['tags'] = [it.strip() for it in el['content'].split(',')]

        el = soup.find('meta', attrs={"property": "og:url"})
        if el:
            item['url'] = el['content']

        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['image'] = el['content']

        el = soup.find('meta', attrs={"property": "og:description"})
        if el:
            item['summary'] = el['content']
        else:
            el = soup.find('meta', attrs={"name": "description"})
            if el:
                item['summary'] = el['content']

        if '/video/' in url:
            # These are Youtube videos
            if not media_src:
                el = soup.find('meta', attrs={"property": "og:video"})
                if el:
                    media_src = el['content']
            if media_src:
                item['content_html'] = utils.add_embed(media_src)
        else:
            if not media_src:
                el = soup.find('source', attrs={"type": "audio/mp3"})
                if el:
                    media_src = el['content']
            if media_src:
                if media_src.startswith('/'):
                    media_src = 'https://www.scientificamerican.com' + media_src
                item['content_html'] = utils.add_image(item['image'])
                item['content_html'] += '<div>&nbsp;</div><table><tr><td style="width:48px;"><a href="{}"><img src="{}/static/play_button-48x48.png" style="width:100%;"/></a></td>'.format(media_src, config.server)
                item['content_html'] += '<td><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div>By {}</div></td></tr></table>'.format(item['url'], item['title'], item['author']['name'])
                if item.get('summary'):
                    item['content_html'] += '<p>{}</p>'.format(item['summary'])

        el = soup.find(class_='transcript__inner')
        if el:
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div><h3>Transcript</h3>' + el.decode_contents()
        return item

    el = soup.find('script', id='__DATA__')
    if not el:
        logger.warning('unable to find __DATA__ in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    data_json = json.loads(el.string[i:j].replace('\\\\', '\\'))
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    article_json = data_json['initialData']['article']

    item['id'] = article_json['mura_contentid']
    item['url'] = 'https://www.scientificamerican.com' + article_json['url']
    item['title'] = article_json['title']

    dt_rel = datetime.fromisoformat(article_json['release_date'])
    dt = datetime.fromisoformat(article_json['published_at_date_time']).replace(tzinfo=dt_rel.tzinfo).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updated_at_date_time']).replace(tzinfo=dt_rel.tzinfo).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in article_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('primary_category'):
        item['tags'].append(article_json['primary_category'])
    if article_json.get('subcategory'):
        item['tags'].append(article_json['subcategory'])
    if article_json.get('categories'):
        item['tags'] += [x for x in article_json['categories'] if x not in item['tags']]
    if article_json.get('tags'):
        item['tags'] += [x for x in article_json['tags'] if x not in item['tags']]

    item['content_html'] = ''
    if article_json.get('summary'):
        item['summary'] = article_json['summary']
        item['content_html'] += '<p><em>{}</em></p>'.format(BeautifulSoup(article_json['summary'], 'html.parser').get_text())

    if article_json.get('image_url'):
        item['image'] = article_json['image_url']
        if article_json.get('media_type') and article_json['media_type'] == 'video':
            item['content_html'] += utils.add_embed(article_json['media_url'])
        else:
            caption = ''
            if article_json.get('image_caption'):
                if article_json['image_caption'].startswith('<p'):
                    caption += BeautifulSoup(article_json['image_caption'], 'html.parser').p.decode_contents()
                else:
                    caption += article_json['image_caption']
            if article_json.get('image_credits'):
                if caption:
                    if not caption.endswith('.'):
                        caption += '. '
                    else:
                        caption += ' '
                caption += 'Credit: '
                if article_json['image_credits'].startswith('<p'):
                    caption += BeautifulSoup(article_json['image_credits'], 'html.parser').p.decode_contents()
                else:
                    caption += article_json['image_credits']
            item['content_html'] += utils.add_image(item['image'], caption)

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('media_type') and article_json['media_type'] == 'podcast':
        item['content_html'] += utils.add_embed(article_json['media_url'])

    for content in article_json['content']:
        if content['type'] == 'paragraph' or content['type'] == 'heading':
            if re.search(r'^(<b>READ MORE</b>:|\[<i>Read more:)', content['content']):
                continue
            item['content_html'] += '<{0}>{1}</{0}>'.format(content['tag'], content['content'])
        elif content['type'] == 'image':
            soup = BeautifulSoup(content['content'], 'html.parser')
            if soup.img:
                if soup.img.get('srcset'):
                    img_src = utils.image_from_srcset(soup.img['srcset'], 1200)
                else:
                    img_src = soup.img['src']
                if soup.figcaption:
                    caption = soup.figcaption.decode_contents()
                else:
                    caption = ''
                item['content_html'] += utils.add_image(img_src, caption)
        else:
            logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
