import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if '/redirect/' in img_src:
        img_src = utils.get_redirect_url(img_src)
    return utils.clean_url(img_src) + '?w={}'.format(width)


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://webapi.wral.com/story/{}/{}/'.format(paths[-2], paths[-1])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    story_json = api_json['data']['root']
    item = {}
    item['id'] = story_json['id']

    link = next((it for it in story_json['platformData']['meta'] if it.get('tag') and it['tag'] == 'link' and it['rel'] == 'canonical'), None)
    if link:
        item['url'] = link['href']
    else:
        item['url'] = '{}://{}{}'.format(split_url['scheme'], split_url['netloc'], story_json['url'])

    item['title'] = story_json['headline']

    dt = datetime.fromisoformat(story_json['published']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['updated']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    if story_json.get('byline'):
        item['author'] = {"name": re.sub(r'^By ', '', story_json['byline'])}
    elif story_json.get('contributors'):
        authors = []
        for author in story_json['contributors']:
            if author.get('members'):
                for it in author['members']:
                    if author.get('role'):
                        authors.append('{} ({})'.format(it['name'], author['role']))
                    else:
                        authors.append(it['name'])
            elif it.get('role'):
                authors.append('{} ({})'.format(author['name'], author['role']))
            else:
                authors.append(author['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author'] = {"name": split_url.netloc}

    item['tags'] = []
    if story_json.get('section'):
        item['tags'].append(story_json['section']['caption'])
    if story_json.get('tags'):
        for it in story_json['tags']:
            item['tags'].append(it['tagCanonicalValue'])

    item['content_html'] = ''
    if story_json.get('abstract'):
        item['summary'] = story_json['abstract']
        item['content_html'] += '<p><em>' + story_json['abstract'] + '</em></p>'

    if story_json['type'] == 'video':
        item['_image'] = resize_image(story_json['videoParams']['poster'])
        item['content_html'] += utils.add_video(story_json['videoParams']['sources']['hls']['src'], story_json['videoParams']['sources']['hls']['type'], item['_image'], story_json['videoParams']['title'])
        if 'embed' not in args and story_json.get('transcript'):
            item['content_html'] += '<h3>Transcript</h3><div>' + story_json['transcript'] + '</div>'
        return item
    elif story_json['type'] == 'image_gallery':
        for it in story_json['relatedAssets']:
            if it['type'] == 'image':
                if not item.get('_image'):
                    item['_image'] = resize_image(it['image']['default']['url'])
                item['content_html'] += utils.add_image(resize_image(it['image']['default']['url']), it['abstract'])
    else:
        if story_json.get('relatedAssets') and (story_json['relatedAssets'][0]['type'] == 'image' or story_json['relatedAssets'][0]['type'] == 'video'):
            if story_json['relatedAssets'][0]['type'] == 'image':
                item['_image'] = resize_image(story_json['relatedAssets'][0]['image']['default']['url'])
                item['content_html'] += utils.add_image(item['_image'], story_json['relatedAssets'][0].get('abstract'))
            elif story_json['relatedAssets'][0]['type'] == 'video':
                item['_image'] = resize_image(story_json['relatedAssets'][0]['videoParams']['poster'])
                item['content_html'] += utils.add_video(story_json['relatedAssets'][0]['videoParams']['sources']['hls']['src'], story_json['relatedAssets'][0]['videoParams']['sources']['hls']['type'], item['_image'], story_json['relatedAssets'][0]['videoParams']['title'])
        elif story_json.get('image') and story_json['image'].get('default'):
            item['_image'] = story_json['image']['default']['url'] + '?w=1000'
            item['content_html'] += utils.add_image(item['_image'])

        for content in story_json['body']:
            if content['type'] == 'html' or content['type'] == 'text':
                item['content_html'] += '<p>' + content['content'] + '</p>'
            elif content['type'] == 'video':
                item['content_html'] += utils.add_video(content['videoParams']['sources']['hls']['src'], content['videoParams']['sources']['hls']['type'], resize_image(content['videoParams']['poster']), content['videoParams']['title'])
            elif content['type'] == 'oembed':
                item['content_html'] += utils.add_embed(content['url'])
            elif content['type'] == 'image_gallery':
                item['content_html'] += utils.add_image(resize_image(content['image']['default']['url']), content['headline'], link=content['url'])
            elif content['type'] == 'outbrain' or content['type'] == 'story':
                continue
            elif content['type'] == 'button' and 'suggest-a-correction' in content['url']:
                continue
            else:
                logger.warning('unhandled body content type {} in {}'.format(content['type'], item['url']))

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
