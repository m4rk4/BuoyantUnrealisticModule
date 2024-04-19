import pytz, re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import instagram

import logging

logger = logging.getLogger(__name__)


def make_post(post, is_parent, is_quoted=False):
    if is_quoted:
        avatar = '{}/image?url={}&width=32&height=32&mask=ellipse'.format(config.server, quote_plus(post['user']['profile_pic_url']))
    else:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(post['user']['profile_pic_url']))

    if post['user']['is_verified'] == True:
        verified_icon = ' &#9989;'
    else:
        verified_icon = ''

    user_url = 'https://www.threads.net/@{}'.format(post['user']['username'])
    post_url = user_url + '/post/' + post['code']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(post['taken_at'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    post_date = '{}/{}/{}'.format(dt.month, dt.day, dt.year)

    logo = '<a href="{}"><img src="https://static.cdninstagram.com/rsrc.php/v3/ye/r/eJ0zF04lTq5.png" style="width:100%;"/></a>'.format(post_url)

    text_html = ''
    if post.get('caption'):
        text_html = post['caption']['text'].replace('\n', '<br/>')
        def sub_links(matchobj):
            m = re.search(r'https?://([^/]+)(/.*)', matchobj.group(1))
            path = m.group(2)
            if len(path) > 8:
                path = path[:8] + '…'
            return '<a href="{}">{}{}</a>'.format(matchobj.group(1), m.group(1), path)
        text_html = re.sub(r'(https?://[^\s]+)', sub_links, text_html)
        text_html = re.sub(r'(@\w+)\b', r'<a href="https://www.threads.net/\1">\1</a>', text_html)

    media_html = ''
    if post.get('image_versions2') and post['image_versions2'].get('candidates'):
        image = utils.closest_dict(post['image_versions2']['candidates'], 'width', 1440)
        img_src = '{}/image?url={}&width=640'.format(config.server, quote_plus(image['url']))
        media_html += '<div><a href="{}"><img width="100%" style="border-radius:10px" src="{}" /></a></div>'.format(image['url'], img_src)

    card_html = ''
    if post.get('text_post_app_info') and post['text_post_app_info'].get('link_preview_attachment'):
        if post['text_post_app_info']['link_preview_attachment']['url'].startswith('https://l.threads.net'):
            params = parse_qs(urlsplit(post['text_post_app_info']['link_preview_attachment']['url']).query)
            card_link = params['u'][0]
        else:
            card_link = post['text_post_app_info']['link_preview_attachment']['url']
        card_desc = '<div style="margin:8px; padding-bottom:8px;"><small>{}</small>'.format(post['text_post_app_info']['link_preview_attachment']['display_url'])
        if post['text_post_app_info']['link_preview_attachment'].get('title'):
            card_desc += '<br/><a href="{}"><b>{}</b></a></div>'.format(card_link, post['text_post_app_info']['link_preview_attachment']['title'])
        card_desc += '</div>'
        if post['text_post_app_info']['link_preview_attachment'].get('image_url'):
            card_html += utils.add_image(post['text_post_app_info']['link_preview_attachment']['image_url'], '', link=card_link, img_style="border-top-left-radius:10px; border-top-right-radius:10px;", fig_style="margin:0; padding:0; border:1px solid black; border-radius:10px;", desc=card_desc)
        else:
            card_html = '<div style="margin:0; padding:0; border:1px solid black; border-radius:10px;">' + card_desc + '</div>'

    quoted_html = ''
    if post.get('text_post_app_info') and post['text_post_app_info'].get('share_info') and post['text_post_app_info']['share_info'].get('quoted_post'):
        quoted_html = make_post(post['text_post_app_info']['share_info']['quoted_post'], False, True)

    if is_quoted:
        post_html = '<table style="font-size:0.95em; width:100%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
        post_html += '<tr><td style="width:36px;"><a href="{}"><img src="{}" /></a></td><td><a style="text-decoration:none;" href="{}"><b>{}</b></a>{} <a style="text-decoration:none;" href="{}">{}</a></td><td></td></tr>'.format(
            user_url, avatar, user_url, post['user']['username'], verified_icon, post_url, post_date)
        if text_html:
            post_html += '<tr><td colspan="2" style="padding:1em 0 1em 0;">{}</td></tr>'.format(text_html)
        if media_html:
            post_html += '<tr><td colspan="2" style="padding:1em 0 1em 0;">{}</td></tr>'.format(media_html)
        if card_html:
            post_html += '<tr><td colspan="2" style="padding:1em 0 1em 0;">{}</td></tr>'.format(card_html)
        if quoted_html:
            post_html += '<tr><td colspan="2" style="padding:1em 0 1em 0;">{}</td></tr>'.format(quoted_html)
        post_html += '</table>'
    elif is_parent:
        post_html = '<tr style="font-size:0.95em;"><td style="width:56px;"><a href="{}"><img src="{}" /></a></td><td colspan="2"><a style="text-decoration:none;" href="{}"><b>{}</b></a>{} <a style="text-decoration:none;" href="{}">{}</a></td></tr>'.format(
            user_url, avatar, user_url, post['user']['username'], verified_icon, post_url, post_date)
        post_html += '<tr><td colspan="3" style="padding:0 0 0 24px;"><table style="font-size:0.95em; padding:0 0 0 24px; border-left:2px solid rgb(196, 207, 214);">'
        if text_html:
            post_html += '<tr><td style="padding:1em 0 1em 0;">{}</td></tr>'.format(text_html)
        if media_html:
            post_html += '<tr><td style="padding:1em 0 1em 0;">{}</td></tr>'.format(media_html)
        if card_html:
            post_html += '<tr><td style="padding:1em 0 1em 0;">{}</td></tr>'.format(card_html)
        if quoted_html:
            post_html += '<tr><td style="padding:1em 0 1em 0;">{}</td></tr>'.format(quoted_html)
        post_html += '</table></td></tr>'
    else:
        post_html = '<tr><td style="width:56px;"><a href="{}"><img src="{}" /></a></td><td><a style="text-decoration:none;" href="{}"><b>{}</b></a>{} <a style="text-decoration:none;" href="{}">{}</a></td><td style="width:32px;">{}</td></tr>'.format(
            user_url, avatar, user_url, post['user']['username'], verified_icon, post_url, post_date, logo)
        if text_html:
            post_html += '<tr><td colspan="3" style="padding:1em 0 1em 0;">{}</td></tr>'.format(text_html)
        if media_html:
            post_html += '<tr><td colspan="3" style="padding:1em 0 1em 0;">{}</td></tr>'.format(media_html)
        if card_html:
            post_html += '<tr><td colspan="3" style="padding:1em 0 1em 0;">{}</td></tr>'.format(card_html)
        if quoted_html:
            post_html += '<tr><td colspan="3" style="padding:1em 0 1em 0;">{}</td></tr>'.format(quoted_html)
    return post_html


def get_content(url, args, site_json, save_debug=False):
    clean_url = utils.clean_url(url)
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    post_data, profile_data = instagram.get_ig_post_data(clean_url, False, save_debug)
    if not post_data:
        return None
    if save_debug:
        utils.write_file(post_data, './debug/threads.json')

    thread_json = post_data['data']['data']['edges'][0]['node']
    for it in thread_json['thread_items']:
        if it['post']['code'] == paths[-1]:
            post_json = it['post']

    item = {}
    item['id'] = thread_json['id']
    item['url'] = clean_url
    item['title'] = '@' + post_json['user']['username']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(post_json['taken_at'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": post_json['user']['username']}

    if post_json.get('caption'):
        item['summary'] = post_json['caption']['text']
        if len(post_json['caption']['text']) > 50:
            item['title'] += ' : ' + re.sub(r'^(.{50}[^\s]*)(.*)', r'\1…', post_json['caption']['text'], flags=re.S)
        else:
            item['title'] += ' : ' + post_json['caption']['text']

    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'

    done = False
    for i, edge in enumerate(post_data['data']['data']['edges']):
        for it in edge['node']['thread_items']:
            if i == 0:
                if it['post']['code'] == paths[-1]:
                    item['content_html'] += make_post(it['post'], False)
                else:
                    item['content_html'] += make_post(it['post'], True)
            else:
                if it['post']['user']['username'] == item['author']['name']:
                    item['content_html'] += make_post(it['post'], True)
                else:
                    done = True
                    break
        if done:
            break

    item['content_html'] += '</table><div>&nbsp;</div>'
    return item