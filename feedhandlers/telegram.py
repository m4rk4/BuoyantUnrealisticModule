import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://t.me/durov/43?embed=1&mode=tme
    embed_html = utils.get_url_html(utils.clean_url(url) + '?embed=1&mode=tme')
    if not embed_html:
        return None
    if save_debug:
        utils.write_file(embed_html, './debug/debug.html')

    soup = BeautifulSoup(embed_html, 'html.parser')

    item = {}
    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border-collapse:collapse; border:1px solid black;">'

    el = soup.find(class_='tgme_widget_message')
    if el and el.get('data-post'):
        item['id'] = el['data-post']
        item['url'] = 'https://t.me/' + el['data-post']
    else:
        # item['content_html'] += '<div><a href="{}">Telegram post not found</a></div>'.format(url)
        logger.warning('Telegram post not found ' + url)
        return None

    el = soup.find(class_='tgme_widget_message_user_photo')
    if el and el.img:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(el.img['src']))
    else:
        avatar = '{}/imagewidth=48&height=48&mask=ellipse'

    el = soup.find(class_='tgme_widget_message_owner_name')
    if el:
        item['author'] = {}
        item['author']['name'] = el.span.get_text()
        if el.get('href'):
            author_link = '<a href="{}"><b>{}</b></a>'.format(el['href'], item['author']['name'])
        else:
            author_link = '<b>{}</b>'.format(item['author']['name'])
        item['title'] = 'A post from {}'.format(item['author']['name'])

        verified_icon = ''
        el = soup.find(class_='tgme_widget_message_owner_labels')
        if el:
            it = el.find(class_='verified-icon')
            if it and it.get_text().strip():
                verified_icon = ' &#9989;'

        item['content_html'] += '<tr><td style="width:48px;"><img src="{}"/></td><td>{}{}</td><td style="width:32px;"><a href="{}"><img src="{}/static/telegram.png"/></a></td></tr>'.format(avatar, author_link, verified_icon, item['url'], config.server)

    el = soup.find(class_='tgme_widget_message_reply')
    if el:
        link = el['href']
        item['content_html'] += '<tr><td colspan="3"><table style="width:100%; font-size:0.9em; border-left:3px solid #64b5ef; margin-left:8px;"><tr>'
        it = el.find(class_='tgme_widget_message_reply_thumb')
        if it:
            m = re.search(r'background-image:url\(\'([^\']+)\'\)', it['style'])
            if m:
                poster = '{}/image?url={}&crop=0&width=32'.format(config.server, quote_plus(m.group(1)))
                item['content_html'] += '<td style="width:32px; vertical-align:top;"><a href="{}"><img src="{}" style="width:100%;"/></a></td>'.format(el['href'], poster)
        item['content_html'] += '<td>'
        it = el.find(class_='tgme_widget_message_author_name')
        if it:
            item['content_html'] += '<div><a href="{}"><b>{}</b></a></div>'.format(el['href'], it.get_text().strip())
        it = el.find(class_='tgme_widget_message_metatext')
        if it:
            m = re.search(r'\S{50}|(\S.{0,48}\S(?!\S))', it.get_text().strip())
            if m:
                item['content_html'] += '<div>{}…</div>'.format(m.group(1))
            #item['content_html'] += '<div>{}</div>'.format(it.decode_contents())
        item['content_html'] += '</td></tr></table></td></tr>'

    el = soup.find('a', class_='tgme_widget_message_document_wrap')
    if el:
        it = el.find(class_='tgme_widget_message_document_title')
        item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><div><div style="display:inline-block; vertical-align:middle; font-size:3em; margin-right:8px;">🗎</div><div style="display:inline-block; vertical-align:middle;"><a href="{}">{}</a>'.format(el['href'], it.get_text().strip())
        it = el.find(class_='tgme_widget_message_document_extra')
        if it:
            item['content_html'] += '<br/><small>{}</small>'.format(it.get_text().strip())
        item['content_html'] += '</div></div></td></tr>'

    has_media = False
    for el in soup.find_all(class_=['tgme_widget_message_photo_wrap', 'tgme_widget_message_video_player']):
        has_media = True
        if 'tgme_widget_message_photo_wrap' in el['class']:
            item['content_html'] += '<tr><td colspan="3" style="padding:0;">'
            if el.get('style'):
                m = re.search(r'background-image:url\(\'([^\']+)\'\)', el['style'])
                if m:
                    item['content_html'] += '<img src="{}" style="width:100%;"/>'.format(m.group(1))
                else:
                    logger.warning('unhandled tgme_widget_message_photo_wrap in ' + url)
            item['content_html'] += '</td></tr>'
        elif 'tgme_widget_message_video_player' in el['class']:
            item['content_html'] += '<tr><td colspan="3" style="padding:0;">'
            thumb = ''
            poster = '{}/image?width=640&height=480&overlay=video'.format(config.server)
            it = el.find(class_='tgme_widget_message_video_thumb')
            if it and it.get('style'):
                m = re.search(r'background-image:url\(\'([^\']+)\'\)', it['style'])
                if m:
                    thumb = m.group(1)
                    poster = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(m.group(1)))
            it = el.find('video')
            if it:
                item['content_html'] += '<a href="{}/videojs?src={}&poster={}"><img src="{}" style="width:100%;"/></a>'.format(config.server, quote_plus(it['src']), quote_plus(thumb), poster)
            else:
                item['content_html'] += '<a href="{}"><img src="{}" style="width:100%;"/></a><div><small>View in Telegram</small></div>'.format(item['url'], poster)
            item['content_html'] += '</td></tr>'

    el = soup.find(class_='tgme_widget_message_text')
    if el:
        has_text = True
        if item['title']:
            item['title'] += ': ' + el.get_text()[:50]
        # TODO: fix tg-emoji
        item['content_html'] += '<tr><td colspan="3" style="padding:8px;">{}</td></tr>'.format(el.decode_contents())
    else:
        has_text = False

    el = soup.find(class_='tgme_widget_message_link_preview')
    if el:
        has_link_preview = True
        link = el['href']
        preview_html = ''
        it = el.find(class_='link_preview_site_name')
        if it:
            preview_html += '<div><a href="{}"><small>{}</small></div>'.format(link, it.get_text())
        it = el.find(class_=re.compile(r'link_preview(_right)?_image'))
        if it:
            m = re.search(r'background-image:url\(\'([^\']+)\'\)', it['style'])
            if m:
                preview_html += '<a href="{}"><img src="{}" style="width:100%; border-radius:10px;"/></a>'.format(link, m.group(1))
        it = el.find(class_='link_preview_title')
        if it:
            preview_html += '<div><a href="{}"><b>{}</b></a></div>'.format(link, it.get_text())
        it = el.find(class_='link_preview_description')
        if it:
            preview_html += '<div>{}</div>'.format(it.decode_contents())
        item['content_html'] += '<tr><td colspan="3" style="padding:8px; font-size:0.9em;"><blockquote style="border-left:3px solid #64b5ef; margin:0px; padding-left:8px;">{}</blockquote></td></tr>'.format(preview_html)
    else:
        has_link_preview = False

    if not has_media and not has_text and not has_link_preview:
        item['content_html'] += '<tr><td colspan="3" style="padding:8px; text-align:center;"><a href="{}">View this post in Telegram</a></td></tr>'.format(item['url'])

    el = soup.find('time', class_='datetime')
    if el:
        dt = datetime.fromisoformat(el['datetime'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><small><a href="{}">{}</a></small></td></tr>'.format(item['url'], item['_display_date'])

    item['content_html'] += '</table>'
    return item

