import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_content(blocks):
    content_html = ''
    for block in blocks:
        if block['type'] == 'lead' or block['type'] == 'p':
            content_html += '<p>' + block['data'] + '</p>'
        elif block['type'] == 'h2' or block['type'] == 'h3' or block['type'] == 'h4':
            content_html += '<{0}>{1}</{0}>'.format(block['type'], block['data'])
        elif block['type'] == 'blockquote':
            content_html += utils.add_blockquote(block['data'])
        elif block['type'] == 'quote':
            content_html += utils.add_pullquote(block['data'])
        elif block['type'] == 'ul':
            content_html += '<ul>'
            for it in block['data']:
                content_html += '<li>' + it + '</li>'
            content_html += '</ul>'
        elif block['type'] == 'image':
            captions = []
            if block['data'].get('caption'):
                captions.append(block['data']['caption'])
            if block['data'].get('credit'):
                captions.append(block['data']['credit'])
            img_src = 'https://meduza.io' + block['data']['large_url']
            content_html += utils.add_image(img_src, ' | '.join(captions))
        elif block['type'] == 'audio':
            poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus('https://meduza.io/' + block['data']['cover_url']))
            duration = utils.calc_duration(block['data']['mp3_duration'])
            date = ''
            meta = next((it for it in block['data']['player_blocks'] if it['type'] == 'meta'), None)
            if meta:
                meta_date = next((it for it in meta['data']['components'] if it['type'] == 'datetime'), None)
                if meta_date:
                    dt = datetime.fromtimestamp(meta_date['datetime']).replace(tzinfo=timezone.utc)
                    date = utils.format_display_date(dt, date_only=True) + ' &bull; '
            content_html += '<table><tr><td style="width:128px;"><a href="https://meduza.io{}"><img src="{}" style="width:100%;"/></a></td>'.format(block['data']['mp3_url'], poster)
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold"><a href="https://meduza.io{}">{}</a></div>'.format(block['data']['url'], block['data']['title'])
            content_html += '<div><a href="https://meduza.io{}">{}</a></div>'.format(block['data']['podcast']['url'], block['data']['podcast']['author'])
            content_html += '<div><small>{}{}</small></div></td></tr></table>'.format(date, duration)
        elif block['type'] == 'embed':
            # TODO: vk embed: https://meduza.io/en/feature/2023/12/13/to-build-or-not-to-build
            embed_url = ''
            if block['data']['provider'] == 'youtube':
                m = re.search(r'src="([^"]+)"', block['data']['html'])
                if m:
                    embed_url = m.group(1)
            elif block['data']['provider'] == 'twitter' or block['data']['provider'] == 'telegram':
                m = re.search(r'media-url="([^"]+)"', block['data']['html'])
                if m:
                    embed_url = m.group(1)
            if embed_url:
                content_html += utils.add_embed(embed_url)
            else:
                logger.warning('unhandled embed provider ' + block['data']['provider'])
        elif block['type'] == 'lead_hr':
            content_html += '<hr/>'
        elif block['type'] == 'card_title':
            content_html += '<h2>' + block['data']['text'] + '</h2>'
        elif block['type'] == 'chapter-subtitle':
            content_html += '<div>&nbsp;</div><hr style="width:128px; margin-left:0;"/><div style="font-size:1.1em; font-weight:bold;">{}</div>'.format(block['data'])
        elif block['type'] == 'grouped':
            content_html += render_content(block['data'])
        elif block['type'] == 'material_note':
            if block.get('data'):
                content_html += '<div>&nbsp;</div><hr style="width:128px; margin-left:0;"/>'
                content_html += render_content(block['data'])
        elif block['type'] == 'note_caption':
            content_html += '<div>{}</div>'.format(block['data'])
        elif block['type'] == 'note_credit':
            content_html += '<div><small>{}</small></div>'.format(block['data'])
        elif block['type'] == 'share' and block['data'].get('pdf'):
            content_html += '<div>&nbsp;</div><hr style="width:128px; margin-left:0;"/><div><a href="https://meduza.io{}">Download a pdf of this story.</a></div>'.format(block['data']['pdf']['standard']['path'])
        elif block['type'] == 'related' or block['type'] == 'related_rich' or block['type'] == 'beet_subscription' or block['type'] == 'brief_subscription' or block['type'] == 'donation':
            pass
        else:
            logger.warning('unhandled block type ' + block['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://meduza.io/api/w5' + split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['root']['url']
    item['url'] = api_json['root']['og']['url']
    item['title'] = api_json['root']['title']

    # Not sure of the timezone
    dt = datetime.fromtimestamp(api_json['root']['datetime']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if api_json['root'].get('source'):
        item['author'] = {
            "name": api_json['root']['source']['name']
        }
    elif api_json['root'].get('audio') and api_json['root']['audio'].get('podcast'):
        item['author'] = {
            "name": api_json['root']['audio']['podcast']['author']
        }
    if 'author' in item:
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if api_json['root'].get('tag'):
        item['tags'].append(api_json['root']['tag']['name'])
    if api_json['root']['og'].get('keywords'):
        item['tags'] += [it.strip() for it in api_json['root']['og']['keywords'].split(',')]
    if not item.get('tags'):
        del item['tags']

    if api_json['root']['og'].get('description'):
        item['summary'] = api_json['root']['og']['description']

    item['content_html'] = ''
    if api_json['root'].get('second_title'):
        item['content_html'] += '<p><em>{}</em></p>'.format(api_json['root']['second_title'])

    if api_json['root']['og'].get('image'):
        item['image'] = api_json['root']['og']['image']
        if api_json['root']['layout'] == 'card':
            item['content_html'] += utils.add_image(item['image'])

    if api_json['root']['content'].get('lead'):
        lead_html = ''
        for content in api_json['root']['content']['lead']:
            if content['type'] == 'rich_title':
                lead_html += '<h2>{}</h2>'.format(content['data']['first'])
                if content['data'].get('second'):
                    lead_html += '<p><em>{}</em></p>'.format(content['data']['second'])
            elif content['type'] == 'meta':
                for component in content['data']['components']:
                    if component['type'] == 'datetime':
                        dt = datetime.fromtimestamp(component['datetime']).replace(tzinfo=timezone.utc)
                        lead_html = '<div>Update: {}</div>'.format(utils.format_display_date(dt)) + lead_html
            elif content['type'] == 'important_lead':
                lead_html += render_content(content['data'])
            elif content['type'] == 'tag':
                pass
        item['content_html'] += lead_html

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if api_json['root']['content'].get('blocks'):
        item['content_html'] += render_content(api_json['root']['content']['blocks'])

    if api_json['root']['content'].get('broadcast'):
        for id in api_json['root']['content']['broadcast']['items_ids']:
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            content = api_json['root']['content']['broadcast']['items'][id]
            if content.get('meta') and content['meta'].get('published_at'):
                dt = datetime.fromtimestamp(content['meta']['published_at']).replace(tzinfo=timezone.utc)
                item['content_html'] += '<div>Update: {}</div>'.format(utils.format_display_date(dt))
            if content.get('blocks'):
                item['content_html'] += render_content(content['blocks'])

    if api_json['root']['content'].get('cards'):
        if api_json['root']['content'].get('table_of_contents'):
            item['content_html'] += '<h3>Contents:</h3><ol>'
            for it in api_json['root']['content']['table_of_contents']:
                item['content_html'] += '<li>{}</li>'.format(it)
            item['content_html'] += '</ol>'
        for card in api_json['root']['content']['cards']:
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>' + render_content(card['blocks'])

    if api_json['root']['content'].get('footnotes'):
        item['content_html'] += '<div>&nbsp;</div><hr/>'
        for block in api_json['root']['content']['footnotes'].values():
            if block.get('title'):
                item['content_html'] += '<h3>{}</h3>'.format(block['title'])
            if block.get('body'):
                item['content_html'] += block['body']

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
