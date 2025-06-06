import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote, urlsplit

import config, utils
from feedhandlers import datawrapper, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    if width == 0:
        return utils.clean_url(img_src)
    return utils.clean_url(img_src) + '?width=' + str(width)


def get_img_src_caption(image, width):
    if image.get('src'):
        img_src = resize_image(image['src'], width)
    elif image.get('s3id'):
        img_src = resize_image(image['cdnLocation'] + '/' + image['s3id'], width)
    else:
        img_src = ''
        logger.warning('unknown image src for image ' + image['_id'])
    captions = []
    if image.get('title'):
        captions.append(image['title'])
    if image.get('credit'):
        captions.append(image['credit'])
    return img_src, ' | '.join(captions)


def add_image(image, width=1200):
    img_src, caption = get_img_src_caption(image, width)
    return utils.add_image(img_src, caption)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    story_json = utils.get_url_json('https://' + split_url.netloc + '/feed' + split_url.path)
    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item[id] = story_json['_id']
    item['url'] = 'https://' + split_url.netloc + story_json['link']
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['published'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('updatedAt'):
        dt = datetime.fromisoformat(story_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": "{} {}".format(x['firstName'], x['lastName'])} for x in story_json['byLines']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if story_json.get('categories'):
        item['tags'] += [x['title'] for x in story_json['categories']]
    if story_json.get('entities'):
        item['tags'] += [x['text'] for x in story_json['entities']]

    item['content_html'] = ''
    if story_json.get('summary'):
        item['summary'] = story_json['summary']
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    lede = False
    media_html = ''
    if story_json.get('videos'):
        for i, media in enumerate(story_json['videos']):
            if i == 0:
                item['image'] = media['poster']
                item['content_html'] += utils.add_video(media['url'], 'application/x-mpegURL', media['poster'], media['title'])
                lede = True
            else:
                media_html += utils.add_video(media['url'], 'application/x-mpegURL', media['poster'], media['title'])

    if story_json.get('images'):
        for i, media in enumerate(story_json['images']):
            if i == 0 and not lede:
                if media.get('src'):
                    item['image'] = resize_image(media['src'])
                elif media.get('s3id'):
                    item['image'] = resize_image(media['cdnLocation'] + '/' + media['s3id'])
                item['content_html'] += add_image(media)
            else:
                media_html += add_image(media)

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    body = BeautifulSoup(story_json['body'], 'html.parser')
    if story_json.get('location'):
        el = body.find('p', recursive=False)
        new_html = '<strong>' + story_json['location'] + ' &ndash; '
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert(0, new_el)

    for el in body.find_all(class_='gnm-iframely'):
        new_html = ''
        data = base64.b64decode(el['data-src']).decode()
        # print(data)
        m = re.search(r'data-iframely-url="([^"]+)', data)
        if not m:
            m = re.search(r'iframe src="([^"]+)', data)
        if m:
            params = parse_qs(urlsplit(m.group(1)).query)
            if 'url' in params:
                embed_url = params['url'][0]
                # print(embed_url)
                if 'fuelmedia.io' in embed_url:
                    m = re.search(r'/([0-9a-f\-]+)\.m3u8', embed_url)
                    poster = 'https://fueltools-prod01-v1-fast.fuelmedia.io/mrss/image?EntityId={}&EntityType=Clip&ContentType=jpg'.format(m.group(1))
                    new_html = utils.add_video(embed_url, 'application/x-mpegURL', poster, '')
                else:
                    new_html = utils.add_embed(embed_url)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            it = el.find_parent('p')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)
        else:
            logger.warning('unhandled gnm-iframely in ' + item['url'])

    for el in body.find_all(class_='viking-slideshow'):
        new_html = ''
        slideshow = utils.get_url_json('https://' + split_url.netloc + '/feed/slideshow/' + el['data-src'])
        if slideshow:
            item['_gallery'] = []
            gallery_url = config.server + '/gallery?url=' + quote(item['url'])
            new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url)
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for image in slideshow['images']:
                img_src, caption = get_img_src_caption(image, 0)
                thumb, caption = get_img_src_caption(image, 800)
                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
            new_html += '</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            it = el.find_parent('p')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)

    for el in body.find_all('blockquote', recursive=False):
        el['style'] = 'border-left:3px solid light-dark(#ccc,#333); margin:1.5em 10px; padding:0.5em 10px;'

    for el in body.select('em', string=re.compile(r'^(>>>|LEARN MORE:|RELATED:)', flags=re.I)):
        it = el.find_parent('p')
        if it:
            it.decompose()

    item['content_html'] += str(body)

    if media_html:
        item['content_html'] += '<h3>Additional media:</h3>' + media_html

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    # TODO: homepage feed
    # https://www.newson6.com/feed/category/all
    # https://www.newson6.com/feed/mostPopularStories
    if 'category' not in paths:
        page_html = utils.get_url_html(url)
        if page_html:
            page_soup = BeautifulSoup(page_html, 'lxml')
            el = page_soup.find('a', class_='btn', href=re.compile(r'/category/'))
            if el:
                paths = list(filter(None, urlsplit(el['href']).path[1:].split('/')))

    if 'category' in paths:
        # feed_stories = utils.get_url_json('https://' + split_url.netloc + '/feed/storiesByCategoryName/' + paths[-1])
        i = paths.index('category')
        feed_stories = utils.get_url_json('https://' + split_url.netloc + '/feed/storiesByCategoryId/' + paths[i + 1])
        if not feed_stories:
            return None
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    if save_debug:
        utils.write_file(feed_stories, './debug/feed.json')

    n = 0
    feed_items = []
    for story in feed_stories['stories']:
        story_url = 'https://' + split_url.netloc + story['link']
        if save_debug:
            logger.debug('getting content for ' + story_url)
        # Categories and entities are only listed by id, so need to fetch the story anyway
        # item = get_story(story, story_url, args, site_json, save_debug)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_stories['title'] + ' | ' + split_url.netloc
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed