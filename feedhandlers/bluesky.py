import json, pytz, re, requests
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_profile(actor_did):
    return utils.get_url_json('https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=' + actor_did)


def get_post_thread(uri):
    api_url = 'https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=' + quote_plus(uri)
    return utils.get_url_json(api_url)


def get_content(url, args, site_json, save_debug=False):
    # https://docs.bsky.app/docs/api/app-bsky-feed-get-post-thread
    if url.startswith('at://'):
        post_uri = url
    else:
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        if 'profile' not in paths and 'post' not in paths:
            logger.warning('unhandled url ' + url)
            return None
        i = paths.index('profile')
        post_uri = 'at://' + paths[i + 1]
        i = paths.index('post')
        post_uri += '/app.bsky.feed.post/' + paths[i + 1]
        # api_url = 'https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at%3A%2F%2F{}%2Fapp.bsky.feed.post%2F{}'.format(quote_plus(paths[1]), paths[-1])
    # print(api_url)
    # api_json = utils.get_url_json(api_url)
    api_json = get_post_thread(post_uri)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/bluesky.json')

    item = get_item(api_json['thread']['post'])
    
    if api_json['thread'].get('parent'):
        item['_parents'] = []
        parent = api_json['thread']['parent']
        while parent:
            item['_parents'].insert(0, get_item(parent['post']))
            if parent.get('parent'):
                parent = parent['parent']
            else:
                parent = None

    def add_replies(replies, author_did):
        children = []
        for reply in replies:
            if reply['post']['author']['did'] == author_did:
                children.append(get_item(reply['post']))
                if reply.get('replies'):
                    children += add_replies(reply['replies'], author_did)
        return children
    if api_json['thread'].get('replies'):
        item['_children'] = add_replies(api_json['thread']['replies'], api_json['thread']['post']['author']['did'])

    item['content_html'] = utils.format_social_media_post(item, config.logo_bluesky, avatar_border_radius='50%', icon_verified=config.icon_verified)
    return item


def get_item(post_json):
    if post_json.get('record'):
        post_record = post_json['record']
    elif post_json.get('value'):
        post_record = post_json['value']

    item = {}
    item['id'] = post_json['uri']
    item['url'] = post_json['uri'].replace('at://', 'https://bsky.app/profile/').replace('/app.bsky.feed.post/', '/post/')
    item['title'] = 'Post by @' + post_json['author']['handle']

    if post_record.get('createdAt'):
        dt = datetime.fromisoformat(post_record['createdAt'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "url": "https://bsky.app/profile/" + post_json['author']['handle'],
        "avatar": post_json['author']['avatar'],
        "_username": post_json['author']['handle']
    }
    if post_json['author'].get('displayName'):
        item['author']['name'] = post_json['author']['displayName']
    else:
        item['author']['name'] = post_json['author']['handle'].split(':')[0]
    if post_json['author'].get('verification') and post_json['author']['verification']['verifiedStatus'] == 'valid':
        item['author']['_verified'] = True
    else:
        item['author']['_verified'] = False
    item['authors'] = []
    item['authors'].append(item['author'])

    if post_record.get('text'):
        item['title'] += ': ' + post_record['text']
        if post_record.get('facets'):
            facets = post_record['facets'].copy()
            indices = []
            for facet in facets:
                indices.append(facet['index']['byteStart'])
                indices.append(facet['index']['byteEnd'])
                facet['start_tag'] = ''
                facet['end_tag'] = ''
                for feature in facet['features']:
                    if feature['$type'] == 'app.bsky.richtext.facet#mention':
                        profile = get_profile(feature['did'])
                        if profile:
                            facet['start_tag'] += '<a href="https://bsky.app/profile/{}">'.format(profile['handle'])
                            facet['end_tag'] = '</a>' + facet['end_tag']
                    elif feature['$type'] == 'app.bsky.richtext.facet#tag':
                        facet['start_tag'] += '<a href="https://bsky.app/hashtag/{}">'.format(feature['tag'])
                        facet['end_tag'] = '</a>' + facet['end_tag']
                    elif feature['$type'] == 'app.bsky.richtext.facet#link':
                        facet['start_tag'] += '<a href="{}">'.format(feature['uri'])
                        facet['end_tag'] = '</a>' + facet['end_tag']
                    else:
                        logger.warning('unhandled facet feature type ' + feature['$type'])
                # remove duplicates and sort
                indices = sorted(list(set(indices)))
                n = 0
                post_text = ''
                text_bytes = post_record['text'].encode()
                for i in indices:
                    post_text += text_bytes[n:i].decode()
                    from_facets = list(filter(lambda facets: facets['index']['byteStart'] == i and facets.get('start_tag'), facets))
                    from_facets = sorted(from_facets, key=lambda x: x['index']['byteEnd'])
                    for j, facet in enumerate(from_facets):
                        post_text += facet['start_tag']
                        facet['order'] = i + j
                    to_facets = list(filter(lambda facets: facets['index']['byteEnd'] == i and facets.get('end_tag'), facets))
                    to_facets = sorted(to_facets, key=lambda x: (x['index']['byteStart'], x['order']), reverse=True)
                    for facet in to_facets:
                        post_text += facet['end_tag']
                    n = i
                post_text += text_bytes[n:].decode()
        else:
            post_text = post_record['text']
        item['summary'] = post_text.replace('\n\n', '<br><br>')

    embeds = []
    if post_json.get('embed'):
        if post_json['embed']['$type'].startswith('app.bsky.embed.recordWithMedia'):
            embeds.append(post_json['embed']['media'])
            embeds.append(post_json['embed']['record']['record'])
        else:
            embeds.append(post_json['embed'])
    elif post_json.get('embeds'):
        for embed in post_json['embeds']:
            if embed['$type'].startswith('app.bsky.embed.recordWithMedia'):
                embeds.append(embed['media'])
                embeds.append(embed['record']['record'])
            else:
                embeds.append(embed)
    elif post_record.get('embed'):
        if post_record['embed']['$type'].startswith('app.bsky.embed.recordWithMedia'):
            embeds.append(post_record['embed']['media'])
            embeds.append(post_record['embed']['record'])
        else:
            embeds.append(post_record['embed'])

    item['_gallery'] = []
    for embed in embeds:
        if embed['$type'].startswith('app.bsky.embed.images'):
            for media in embed['images']:
                if 'fullsize' in media:
                    item['_gallery'].append({
                        "src": media['fullsize'],
                        "thumb": media['thumb'],
                        "width": media['aspectRatio']['width'],
                        "height": media['aspectRatio']['height'],
                        "caption": ""
                    })
                elif 'image' in media and media['image']['$type'] == 'blob':
                    item['_gallery'].append({
                        "src": "https://cdn.bsky.app/img/feed_fullsize/plain/" + post_json['author']['did'] + "/" + media['image']['ref']['$link'] + "@jpeg",
                        "thumb": "https://cdn.bsky.app/img/feed_thumbnail/plain/" + post_json['author']['did'] + "/" + media['image']['ref']['$link'] + "@jpeg",
                        "width": media['aspectRatio']['width'],
                        "height": media['aspectRatio']['height'],
                        "caption": ""
                    })
                else:
                    logger.warning('unhandled app.bsky.embed.images image in ' + item['id'])
        elif embed['$type'].startswith('app.bsky.embed.video'):
            item['_gallery'].append({
                "src": embed['playlist'],
                "video_type": "application/x-mpegURL",
                "thumb": embed['thumbnail'],
                "width": embed['aspectRatio']['width'],
                "height": embed['aspectRatio']['height'],
                "caption": ""
            })
        elif embed['$type'].startswith('app.bsky.embed.external'):
            split_url = urlsplit(embed['external']['uri'])
            if split_url.netloc == 'media.tenor.com':
                item['_gallery'].append({
                    "src": "https://t.gifs.bsky.app/" + split_url.path.replace('.gif', 'webm'),
                    "video_type": "video/webm",
                    "thumb": embed['external']['thumb'],
                    "caption": ""
                })
            else:
                link = embed['external']['uri']
                if split_url.netloc == 'bit.ly' or split_url.netloc == 'buff.ly':
                    r = requests.get(embed['external']['uri'], allow_redirects=False)
                    try:
                        link = r.headers['location']
                    except:
                        link = embed['external']['uri']
                else:
                    link = embed['external']['uri']
                item['_card'] = {
                    "url": link,
                    "title": embed['external']['title'],
                }
                if embed['external'].get('thumb'):
                    item['_card']['image'] = embed['external']['thumb']
                if embed['external'].get('description'):
                    item['_card']['summary'] = embed['external']['description']
        elif embed['$type'].startswith('app.bsky.embed.record'):
            if embed.get('record'):
                record = embed['record']
                if record.get('record'):
                    record = record['record']
            elif embed.get('cid'):
                record = embed
            if '#view' not in embed['$type']:
                api_json = get_post_thread(record['uri'])
                if api_json:
                    record = api_json['thread']['post']
            item['_quote'] = get_item(record)

    if len(item['_gallery']) == 0:
        del item['_gallery']
    return item


def make_post(post_json, is_parent=False, is_reply=False, is_quoted=False):
    post_url = post_json['uri'].replace('at://', 'https://bsky.app/profile/').replace('/app.bsky.feed.post/', '/post/')
    author_url = "https://bsky.app/profile/" + post_json['author']['handle']
    dt_loc = datetime.fromisoformat(post_json['record']['createdAt']).astimezone(pytz.timezone(config.local_tz))

    if post_json['record'].get('text'):
        if post_json['record'].get('facets'):
            facets = post_json['record']['facets'].copy()
            indices = []
            for facet in facets:
                indices.append(facet['index']['byteStart'])
                indices.append(facet['index']['byteEnd'])
                facet['start_tag'] = ''
                facet['end_tag'] = ''
                for feature in facet['features']:
                    if feature['$type'] == 'app.bsky.richtext.facet#mention':
                        profile = get_profile(feature['did'])
                        if profile:
                            facet['start_tag'] += '<a href="https://bsky.app/profile/{}">'.format(profile['handle'])
                            facet['end_tag'] = '</a>' + facet['end_tag']
                    elif feature['$type'] == 'app.bsky.richtext.facet#tag':
                        facet['start_tag'] += '<a href="https://bsky.app/hashtag/{}">'.format(feature['tag'])
                        facet['end_tag'] = '</a>' + facet['end_tag']
                    elif feature['$type'] == 'app.bsky.richtext.facet#link':
                        facet['start_tag'] += '<a href="{}">'.format(feature['uri'])
                        facet['end_tag'] = '</a>' + facet['end_tag']
                    else:
                        logger.warning('unhandled facet feature type ' + feature['$type'])
                # remove duplicates and sort
                indices = sorted(list(set(indices)))
                n = 0
                post_text = ''
                text_bytes = post_json['record']['text'].encode()
                for i in indices:
                    post_text += text_bytes[n:i].decode()
                    from_facets = list(filter(lambda facets: facets['index']['byteStart'] == i and facets.get('start_tag'), facets))
                    from_facets = sorted(from_facets, key=lambda x: x['index']['byteEnd'])
                    for j, facet in enumerate(from_facets):
                        post_text += facet['start_tag']
                        facet['order'] = i + j
                    to_facets = list(filter(lambda facets: facets['index']['byteEnd'] == i and facets.get('end_tag'), facets))
                    to_facets = sorted(to_facets, key=lambda x: (x['index']['byteStart'], x['order']), reverse=True)
                    for facet in to_facets:
                        post_text += facet['end_tag']
                    n = i
                post_text += text_bytes[n:].decode()
        else:
            post_text = post_json['record']['text']
    else:
        post_text = ''
    post_text = post_text.replace('\n\n', '<br><br>')

    if post_json['author'].get('displayName'):
        author_name = post_json['author']['displayName']
    else:
        author_name = post_json['author']['handle']

    if is_parent or is_reply:
        colspan = 3
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(post_json['author']['avatar']))
        post_date = '{}/{}/{}'.format(dt_loc.month, dt_loc.day, dt_loc.year)
        post_html = '<tr style="font-size:0.95em;"><td style="width:56px;"><a href="{0}"><img src="{1}" /></td><td colspan="2"><a style="text-decoration:none;" href="{0}"><b>{2}</b> <small>@{3}</small></a> · <a style="text-decoration:none;" href="{4}"><small>{5}</small></a></td></tr>'.format(author_url, avatar, author_name, post_json['author']['handle'], post_url, post_date)
        post_html += '<tr><td colspan="3" style="padding:0 0 0 24px;"><table style="font-size:0.95em; padding:0 0 0 24px; border-left:2px solid rgb(196, 207, 214);">'
    elif is_quoted:
        colspan = 2
        post_html = '<table style="font-size:0.95em; width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#ccc, #333); border-radius:10px;">'
        avatar = '{}/image?url={}&width=32&height=32&mask=ellipse'.format(config.server, quote_plus(post_json['author']['avatar']))
        post_date = '{}/{}/{}'.format(dt_loc.month, dt_loc.day, dt_loc.year)
        post_html += '<tr><td style="width:36px;"><a href="{}"><img src="{}" /></a></td><td><a style="text-decoration:none;" href="{}"><b>{}</b> <small>@{}</small></a> · <a style="text-decoration:none;" href="{}"><small>{}</small></a></td></tr>'.format(author_url, avatar, author_url, author_name, post_json['author']['handle'], post_url, post_date)
    else:
        colspan = 3
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(post_json['author']['avatar']))
        # logo = 'https://bsky.social/about/images/favicon-32x32.png'
        logo = config.icon_bluesky
        post_html = '<tr><td style="width:56px;"><a href="{}"><img src="{}" /></a></td><td><a style="text-decoration:none;" href="{}"><b>{}</b><br/><small>@{}</small></a></td><td style="width:32px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td></tr>'.format(author_url, avatar, author_url, author_name, post_json['author']['handle'], post_url, logo)

    if post_text:
        post_html += '<tr><td colspan="{}" style="padding:1em 0 1em 0;">'.format(colspan) + post_text + '</td></tr>'

    def add_embed(embed):
        if embed['$type'] == 'app.bsky.embed.recordWithMedia':
            return add_embed(embed['media']) + add_embed(embed['record'])

        embed_html = '<tr><td colspan="{}" style="padding:1em 0 1em 0;">'.format(colspan)
        if embed['$type'] == 'app.bsky.embed.record':
            embed_json = utils.get_url_json('https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=' + quote_plus(embed['record']['uri']))
            if embed_json:
                embed_html += make_post(embed_json['thread']['post'], is_quoted=True)
        elif embed['$type'] == 'app.bsky.embed.images':
            if len(embed['images']) == 1:
                img_uri = '{}/{}@jpeg'.format(post_json['author']['did'], embed['images'][0]['image']['ref']['$link'])
                embed_html += '<div><a href="https://cdn.bsky.app/img/feed_fullsize/plain/{0}" target="_blank"><img src="https://cdn.bsky.app/img/feed_thumbnail/plain/{0}" style="width:100%; border-radius:10px"/></a></div>'.format(img_uri)
            else:
                gallery_images = []
                embed_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for i, image in enumerate(embed['images']):
                    img_uri = '{}/{}@jpeg'.format(post_json['author']['did'], image['image']['ref']['$link'])
                    embed_html += '<div style="flex:1; min-width:200px;"><a href="https://cdn.bsky.app/img/feed_fullsize/plain/{0}" target="_blank"><img src="https://cdn.bsky.app/img/feed_thumbnail/plain/{0}" style="width:100%; border-radius:10px;"/></a></div>'.format(img_uri)
                    gallery_images.append({"src": 'https://cdn.bsky.app/img/feed_fullsize/plain/' + img_uri, "caption": '', "thumb": 'https://cdn.bsky.app/img/feed_thumbnail/plain/' + img_uri})
                if i % 2 == 0:
                    embed_html += '<div style="flex:1; min-width:200px;"></div>'
                embed_html += '</div>'
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                embed_html += '<div style="padding:8px; font-size:0.9em;"><a href="{}" target="_blank">View photo gallery</a></div>'.format(gallery_url)
        elif embed['$type'] == 'app.bsky.embed.video':
            video_src = 'https://video.bsky.app/watch/{}/{}/playlist.m3u8'.format(quote_plus(post_json['author']['did']), embed['video']['ref']['$link'])
            poster = 'https://video.bsky.app/watch/{}/{}/thumbnail.jpg'.format(quote_plus(post_json['author']['did']), embed['video']['ref']['$link'])
            embed_html += '<div><a href="{0}/videojs?src={1}&type=application%2Fx-mpegURL&poster={2}" target="_blank"><img src="{0}/image?url={2}&width=640&overlay=video" style="width:100%; border-radius:10px"/></a></div>'.format(config.server, quote_plus(video_src), poster)
        elif embed['$type'] == 'app.bsky.embed.external':
            if embed['external']['uri'].startswith('https://media.tenor.com/'):
                embed_html += '<div><a href="{0}" target="_blank"><img src="{0}" style="width:100%; border-radius:10px"/></a></div>'.format(embed['external']['uri'])
            elif embed['external']['uri'].startswith('https://www.youtube.com/'):
                ext_item = {
                    "url": embed['external']['uri'],
                    "title": embed['external']['title'],
                    "image": "",
                    "summary": embed['external']['description']
                }
                poster = 'https://cdn.bsky.app/img/feed_thumbnail/plain/{}/{}@jpeg'.format(post_json['author']['did'], embed['external']['thumb']['ref']['$link'])
                ext_item['image'] = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(poster))
                embed_html += utils.format_embed_preview(ext_item, add_space=False)
            else:
                if embed['external']['uri'].startswith('https://docs.google.com/'):
                    ext_html = ''
                else:
                    ext_html = utils.add_embed(embed['external']['uri'])
                if ext_html == '' or ext_html.startswith('<blockquote>'):
                    ext_item = {
                        "url": embed['external']['uri'],
                        "title": embed['external']['title'],
                        "image": "",
                        "summary": embed['external']['description']
                    }
                    if embed['external'].get('thumb'):
                        ext_item['image'] = 'https://cdn.bsky.app/img/feed_thumbnail/plain/{}/{}@jpeg'.format(post_json['author']['did'], embed['external']['thumb']['ref']['$link'])
                    embed_html += utils.format_embed_preview(ext_item, content_link=False, add_space=False)
                else:
                    embed_html += re.sub(r'<div>&nbsp;</div>$', '', ext_html)
        else:
            logger.warning('unhandled embed type ' + embed['$type'])
        embed_html += '</td></tr>'
        return embed_html
        
    if post_json['record'].get('embed'):
        post_html += add_embed(post_json['record']['embed'])

    if is_parent or is_reply:
        post_html += '</table></td></tr>'
    elif is_quoted:
        post_html += '</table>'
    else:
        post_time = '{}:{:02d} {}'.format(dt_loc.strftime('%I').lstrip('0'), dt_loc.minute, dt_loc.strftime('%p'))
        post_date = '{}. {}, {}'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)
        post_html += '<tr><td colspan="3" style="padding-bottom:8px;"><a style="text-decoration:none;" href="{}"><small>{} at {}</small></a></td></tr>'.format(post_url, post_date, post_time)
    return post_html