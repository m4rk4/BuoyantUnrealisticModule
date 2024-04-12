import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def add_media(media):
    if media['type'] == 'Photo':
        size = utils.closest_value(media['imageRenderedSizes'], 1000)
        url = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
        media_html = utils.add_image(url, media['flattenedCaption'])
    elif media['type'] == 'Video' and media.get('jwVideoStatus'):
        media_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(media['jwMediaId']))
    elif media['type'] == 'YouTube':
        media_html = utils.add_embed('https://www.youtube.com/watch?v={}'.format(media['externalId']))
    else:
        logger.warning('Unhandled media type {}'.format(media['type']))
        media_html = ''
    return media_html


def get_image_url(img_id, file_ext='.jpeg', img_width=600):
    return 'https://storage.googleapis.com/afs-prod/media/{}/{}{}'.format(img_id, img_width, file_ext)


def get_item(content_data, args, site_json, save_debug=False):
    item = {}
    item['id'] = content_data['id']
    item['url'] = content_data['localLinkUrl']
    item['title'] = content_data['headline']

    dt_pub = None
    if content_data.get('published'):
        dt_pub = datetime.fromisoformat(content_data['published']).replace(tzinfo=timezone.utc)
    dt_mod = None
    if content_data.get('updated'):
        dt_mod = datetime.fromisoformat(content_data['updated']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt_mod.isoformat()
    if not dt_pub and dt_mod:
        dt_pub = dt_mod
    if dt_pub:
        item['date_published'] = dt_pub.isoformat()
        item['_timestamp'] = dt_pub.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)

    if not utils.check_age(item, args):
        return None

    item['author'] = {}
    if content_data.get('bylines'):
        m = re.search(r'^By\s(.*)', content_data['bylines'], flags=re.I)
        if m:
            item['author']['name'] = m.group(1).title().replace('And', 'and')
        else:
            item['author']['name'] = content_data['bylines'].title().replace('And', 'and')
    else:
        item['author']['name'] = 'AP News'

    if content_data.get('tagObjs'):
        item['tags'] = []
        for tag in content_data['tagObjs']:
            item['tags'].append(tag['name'])

    if content_data.get('leadPhotoId'):
        item['_image'] = get_image_url(content_data['leadPhotoId'])

    item['summary'] = content_data['flattenedFirstWords']

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    story_soup = BeautifulSoup(content_data['storyHTML'], 'html.parser')

    for el in story_soup.find_all(class_=['ad-placeholder', 'hub-peek-embed']):
        el.decompose()

    for el in story_soup.find_all(class_='media-placeholder'):
        for media in content_data['media']:
            if media['id'] == el['id']:
                new_html = add_media(media)
                if new_html:
                    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                    el.decompose()
                    break

    for el in story_soup.find_all(class_='social-embed'):
        for embed in content_data['socialEmbeds']:
            if embed['id'] == el['id']:
                new_html = ''
                embed_soup = BeautifulSoup(embed['html'], 'html.parser')
                if embed_soup.iframe:
                    if embed_soup.iframe['src'].startswith('https://interactives.ap.org/embeds/'):
                        new_html = ''
                        src_html = utils.get_url_html(embed_soup.iframe['src'])
                        if src_html:
                            src_soup = BeautifulSoup(src_html, 'html.parser')
                            it = src_soup.find(id='header')
                            if it:
                                title = it.get_text()
                            else:
                                title = ''
                            it = src_soup.find('meta', attrs={"property": "og:image"})
                            if it:
                                new_html = utils.add_image(it['content'], title, link=embed_soup.iframe['src'])
                        if not new_html:
                            if embed_soup.iframe.get('title'):
                                title = embed_soup.iframe['title']
                            else:
                                title = embed_soup.iframe['src']
                            new_html = '<blockquote><b>Embedded content: <a href="{}">{}</a></b></blockquote>'.format(embed_soup.iframe['src'], title)
                    else:
                        new_html = utils.add_embed(embed_soup.iframe['src'])
                elif embed_soup.contents[0].name == 'img':
                    new_html = utils.add_image(embed_soup.img['src'])
                if new_html:
                    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                    el.decompose()
                break

    for el in story_soup.find_all(class_='related-story-embed'):
        for embed in content_data['relatedStoryEmbeds']:
            if embed['id'] == el['id']:
                new_html = '<h4>{}</h4><ul>'.format(embed['introText'])
                for li in embed['contentsList']:
                    title = ''
                    desc = ''
                    if li.get('contentId'):
                        li_json = utils.get_url_json('https://afs-prod.appspot.com/api/v2/content/' + li['contentId'])
                        if li_json:
                            title = li_json['headline']
                            desc = li_json['flattenedFirstWords']
                    else:
                        title, desc = utils.get_url_title_desc(li['url'])
                    new_html += '<li><b><a href="{}">{}</a></b><br />{}</li>'.format(li['url'], title, desc)
                new_html += '</ul>'
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
                break

    for el in story_soup.find_all(class_='hub-link-embed'):
        for embed in content_data['richEmbeds']:
            if embed['id'] == el['id']:
                new_html = '<blockquote><b>{} &ndash; <a href="https://apnews.com/hub/{}">{}</a></b></blockquote'.format(embed['displayName'], embed['tag']['id'], embed['calloutText'])
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
                break

    item['content_html'] = ''
    if content_data.get('leadVideoId'):
        media = next((it for it in content_data['media'] if it['id'] == content_data['leadVideoId']), None)
        if media:
            item['content_html'] = add_media(media)
    elif content_data.get('leadPhotoId'):
        media = next((it for it in content_data['media'] if it['id'] == content_data['leadPhotoId']), None)
        if media:
            item['content_html'] = add_media(media)
    elif item.get('_image'):
        item['content_html'] = utils.add_image(item['_image'])

    item['content_html'] += str(story_soup)

    if content_data.get('media'):
        for media in content_data['media']:
            exists = re.search(media['id'], item['content_html'])
            if not exists and media.get('externalId'):
                exists = re.search(media['externalId'], item['content_html'])
            if not exists:
                item['content_html'] += add_media(media)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    m = re.search('([0-9a-f]+)\/?$', split_url.path)
    if not m:
        logger.warning('unable to parse article id from ' + url)
        return None

    article_json = utils.get_url_json('https://afs-prod.appspot.com/api/v2/content/' + m.group(1))
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    return get_item(article_json, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    if split_url.path.startswith('/hub'):
        tag = split_url.path.split('/')[2]
        feed_url = 'https://afs-prod.appspot.com/api/v2/feed/tag?tags={}'.format(tag)
    else:
        feed_url = 'https://afs-prod.appspot.com/api/v2/feed/tag'

    feed_json = utils.get_url_json(feed_url)
    if not feed_json:
        return None
    if save_debug:
        utils.write_file(feed_json, './debug/debug.json')

    # Loop through each post
    n = 0
    items = []
    for card in feed_json['cards']:
        for content in card['contents']:
            url = 'https://afs-prod.appspot.com/api/v2/content/{}'.format(content['id'])
            if content['contentType'] == 'text':
                item = get_content(url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        items.append(item)
            else:
                logger.warning('unhandled contentType {} in {}'.format(content['contentType'], url))

        for card_feed in card['feed']:
            for content in card_feed['contents']:
                url = 'https://afs-prod.appspot.com/api/v2/content/{}'.format(content['id'])
                if content['contentType'] == 'text':
                    item = get_content(url, args, site_json, save_debug)
                    if item:
                        if utils.filter_item(item, args) == True:
                            items.append(item)
                else:
                    logger.warning('unhandled contentType {} in {}'.format(content['contentType'], url))

    # sort by date
    items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)

    feed = utils.init_jsonfeed(args)

    if 'max' in args:
        n = int(args['max'])
        feed['items'] = items[:n].copy()
    else:
        feed['items'] = items.copy()
    return feed
