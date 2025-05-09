import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    if split_url.netloc != 'imgix.bustle.com':
        return img_src
    return '{}://{}{}?w={}&fit=max&auto=format%2Ccompress'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_image(image, caption=''):
    if image['url'].endswith('gif'):
        return add_video(image, caption)
    img_src = resize_image(image['url'])
    #if 'localhost' in config.server:
    #    img_src = '{}/image?url={}'.format(config.server, quote_plus(img_src))
    if not caption:
        if image.get('attribution'):
            caption = image['attribution']
    return utils.add_image(img_src, caption)


def add_video(video, caption=''):
    if video.get('attribution'):
        if caption:
            caption += ' | ' + video['attribution']
        else:
            caption = video['attribution']
    if video.get('low'):
        video_src = video['low']['url']
    elif video.get('max'):
        video_src = video['max']['url']
    elif video.get('url') and video['url'].endswith('gif'):
        video_src = '{}?w=640&fit=max&fm=mp4'.format(video['url'])
    poster = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(video_src))
    return utils.add_video(video_src, 'video/mp4', poster, caption)


def add_media(media_card):
    media_html = ''
    field_html = ''
    if media_card['fields'].get('caption'):
        caption = render_body(media_card['fields']['caption'])
    else:
        caption = ''
    m = re.search(r'^<p>(.*)</p>$', caption)
    if m:
        caption = m.group(1)
    m = re.search(r'^<h\d>(.*)</h\d>$', caption)
    if m:
        caption = ''
        field_html = '<p>{}</p>'.format(m.group(1))
    if media_card['fields'].get('attribution'):
        if media_card['fields'].get('attributionUrl'):
            attribution = '<a href="{}">{}</a>'.format(media_card['fields']['attributionUrl'], media_card['fields']['attribution'])
        else:
            attribution = media_card['fields']['attribution']
        if caption:
            caption += ' | ' + attribution
        else:
            caption = attribution
    if media_card['media']['__typename'] == 'Image':
        if media_card.get('image'):
            media_html += add_image(media_card['image'], caption)
        else:
            media_html += add_image(media_card['media'], caption)
    elif media_card['media']['__typename'] == 'Video':
        if media_card.get('video'):
            media_html += add_video(media_card['video'], caption)
        else:
            media_html += add_video(media_card['video'], caption)
    else:
        logger.warning('unhandled media type ' + media_card['media']['__typename'])
    if field_html:
        media_html += field_html
    return media_html


def render_card(card, list_index=0):
    card_html = ''
    if not card:
        return card_html

    if card['type'] == 'media':
        card_html += add_media(card)

    elif card['type'] == 'headline':
        field_html = render_body(card['fields']['headline'])
        m = re.search(r'^<[ph]\d?>(.*)</[ph]\d?>$', field_html)
        if m:
            field_html = m.group(1)
            card_html += '<h2 class="headline">{}</h2>'.format(field_html)
        if card['fields'].get('dek'):
            card_html += render_body(card['fields']['dek'])
        if card.get('image'):
            card_html += add_image(card['image'])
        if card.get('video'):
            card_html += add_video(card['video'])

    elif card['type'] == 'paragraph':
        card_html += render_body(card['fields']['paragraph'])
        if card.get('image'):
            card_html += add_image(card['image'])
        if card.get('video'):
            card_html += add_video(card['video'])

    elif card['type'] == 'quote':
        if card.get('image'):
            card_html += add_image(card['image'])
        if card.get('video'):
            card_html += add_video(card['video'])
        field_html = render_body(card['fields']['quote'])
        m = re.search(r'^<p>(.*)</p>$', field_html)
        if m:
            field_html = m.group(1)
        card_html += '<center><h3>{}</h3></center>'.format(field_html)

    elif card['type'] == 'gallery':
        if card['fields'].get('title'):
            field_html = render_body(card['fields']['title'])
            m = re.search(r'^<[ph]\d?>(.*)</[ph]\d?>$', field_html)
            if m:
                field_html = m.group(1)
            card_html += '<h2>{}</h2>'.format(field_html)
        if card['fields'].get('description'):
            card_html += render_body(card['fields']['description'])
        for it in card['fields']['items']:
            item = next(node for node in card['items']['nodes'] if node['id'] == it)
            card_html += add_media(item['card']) + '<br/>'

    elif card['type'] == 'oembed':
        card_html += utils.add_embed(card['oembed']['url'])

    elif card['type'] == 'product':
        poster = '{}/image?url={}&width=128'.format(config.server, quote_plus(card['product']['primaryMedia']['url']))
        if card['product'].get('price'):
            desc = '<h4 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h4>${:.2f} on {}'.format(card['product']['linkUrl'], card['product']['name'], card['product']['price']['amount'] / 100, card['product']['source'])
        else:
            desc = '<h4 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h4>From {}'.format(card['product']['linkUrl'], card['product']['name'], card['product']['source'])
        card_html += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(card['product']['linkUrl'], poster, desc)

    elif card['type'] == 'productCollection':
        if card['fields'].get('title'):
            field_html = render_body(card['fields']['title'])
            m = re.search(r'^<[ph]\d?>(.*)</[ph]\d?>$', field_html)
            if m:
                field_html = m.group(1)
            card_html += '<h2>{}</h2>'.format(field_html)
        for node in card['cardZones']['nodes']:
            card_html += render_card(node['card'])

    elif card['type'] == 'icon':
        field_html = render_body(card['fields']['description'])
        m = re.search(r'^<p>(.*)</p>$', field_html)
        if m:
            field_html = m.group(1)
        card_html += '<center><h3>{}</h3></center>'.format(field_html)
        img_src = '{}/image?url={}&overlay={}&overlay_position=(%2C-1)&width=1200'.format(config.server, quote_plus(card['image']['url']), quote_plus(card['icon']['url']))
        caption = ''
        if card['image'].get('attribution'):
            caption += card['image']['attribution']
        card_html += utils.add_image(img_src, caption)

    elif card['type'] == 'listItem':
        if card['fields'].get('title'):
            field_html = render_body(card['fields']['title'])
            m = re.search(r'^<[ph]\d?>(.*)</[ph]\d?>$', field_html)
            if m:
                field_html = m.group(1)
            if list_index > 0:
                card_html += '<h2>{}. {}</h2>'.format(list_index, field_html)
            else:
                card_html += '<h2>{}</h2>'.format(field_html)
        if card.get('item'):
            card_html += render_card(card['item']['card'])
        card_html += render_body(card['fields']['body'], card['bodyZones'])

    elif card['type'] == 'data' and card.get('image'):
        if card['image'].get('attribution'):
            if card['image'].get('attributionUrl'):
                caption = '<a href="{}">{}</a>'.format(card['image']['attributionUrl'], card['image']['attribution'])
            else:
                caption = card['image']['attribution']
        else:
            caption = ''
        heading = '<div style="text-align:center;">{}</div>'.format(card['fields']['description'])
        heading += '<div style="text-align:center; font-size:1.5em; font-weight:bold;">{}</div>'.format(card['fields']['numeral'].upper())
        card_html += utils.add_image(resize_image(card['image']['url']), caption, heading=heading)

    else:
        logger.warning('unhandled card type ' + card['type'])
    return card_html


def render_markers(markers, markups, atoms):
    render_html = ''
    for marker in markers:
        if marker[0] == 0:
            # MARKUP_MARKER_TYPE
            start_tag = ''
            end_tag = ''
            if len(marker[1]) != 0:
                for i in marker[1]:
                    markup = markups[i]
                    if markup[0] == 'u':
                        start_tag += '<span style="text-transform:uppercase;">'
                        end_tag = '</span>' + end_tag
                    else:
                        start_tag += '<' + markup[0]
                        if len(markup) > 1:
                            for j in range(0, len(markup[1]), 2):
                                start_tag += ' {}="{}"'.format(markup[1][j], markup[1][j + 1])
                        start_tag += '>'
                        end_tag = '</{}>'.format(markup[0]) + end_tag
            render_html += start_tag + marker[3] + end_tag

        elif marker[0] == 1:
            # ATOM_MARKER_TYPE
            atom = atoms[marker[3]]
            if atom[0] == 'soft-return':
                render_html += '<br/>'
            else:
                logger.warning('unhandled ATOM_MARKER_TYPE')
    return render_html


def render_markup_section(section, markups, atoms):
    return '<{0}>{1}</{0}>'.format(section[1], render_markers(section[2], markups, atoms))


def render_body(body, body_zones=None):
    # https://github.com/bustle/mobiledoc-text-renderer
    body_html = ''
    for section in body['sections']:
        if section[0] == 1:
            # MARKUP_SECTION_TYPE
            body_html += render_markup_section(section, body['markups'], body['atoms'])

        elif section[0] == 2:
            # IMAGE_SECTION_TYPE
            logger.warning('unhandled IMAGE_SECTION_TYPE')

        elif section[0] == 3:
            # LIST_SECTION_TYPE
            body_html += '<{}>'.format(section[1])
            for li in section[2]:
                body_html += '<li>' + render_markers(li, body['markups'], body['atoms']) + '</li>'
            body_html += '</{}>'.format(section[1])

        elif section[0] == 10:
            # CARD_SECTION_TYPE
            card = body['cards'][section[1]]
            if card[0] == 'ZoneCard':
                zone_card = next((zone for zone in body_zones if zone['id'] == card[1]['id']), None)
                if zone_card:
                    body_html += render_card(zone_card['card'])

            elif card[0] == 'DividerCard':
                pass

            elif card[0] == 'hr':
                body_html += '<hr/>'

            elif card[0] == 'tpgH2':
                body_html += '<h2>' + card[1]['tpgH2']['title'] + '</h2>'

            elif card[0] == 'tpgImage':
                captions = []
                if card[1]['tpgImage'].get('caption'):
                    captions.append(card[1]['tpgImage']['caption'])
                if card[1]['tpgImage'].get('credit'):
                    captions.append(card[1]['tpgImage']['credit'])
                if not captions and card[1]['tpgImage'].get('title') and not re.search(r'\d+-IMG_\d+|screenshot', card[1]['tpgImage']['title'], flags=re.I):
                    captions.append(card[1]['tpgImage']['title'])
                body_html += utils.add_image(card[1]['tpgImage']['src'], ' | '.join(captions))

            elif card[0] == 'tpgFigure':
                captions = []
                if card[1]['tpgFigure'].get('caption'):
                    captions.append(card[1]['tpgFigure']['caption'])
                elif card[1]['tpgFigure']['image'].get('caption'):
                    captions.append(card[1]['tpgFigure']['image']['caption'])
                if card[1]['tpgFigure']['image'].get('credit') and card[1]['tpgFigure']['image']['credit'] not in captions:
                    captions.append(card[1]['tpgFigure']['image']['credit'])
                body_html += utils.add_image(card[1]['tpgFigure']['image']['src'], ' | '.join(captions))

            elif card[0] == 'tpgGallery':
                for image in card[1]['tpgGallery']:
                    captions = []
                    if image.get('caption'):
                        captions.append(image['caption'])
                    if image.get('credit') and image['credit'] not in captions:
                        captions.append(image['credit'])
                    if image.get('title') and not re.search(r'\d+-IMG_\d+|screenshot', image['title'], flags=re.I):
                        captions.append(image['title'])
                    body_html += utils.add_image(image['src'], ' | '.join(captions))

            elif card[0] == 'tpgYoutube':
                body_html += utils.add_embed('https://www.youtube.com/watch?v=' + card[1]['tpgYoutube']['id'])

            elif card[0] == 'tpgTable':
                body_html += '<table style="width:100%; border-collapse:collapse;">'
                for i, tr in enumerate(card[1]['tpgTable']['rows']):
                    if i % 2 == 0:
                        body_html += '<tr style="line-height:2em; background-color:#ccc;">'
                    else:
                        body_html += '<tr style="line-height:2em;">'
                    for td in tr:
                        body_html += '<td style="border:1px solid black; vertical-align:top;">' + td + '</td>'
                    body_html += '</tr>'
                body_html += '</table>'


            else:
                logger.warning('unhandled card type ' + card[0])

        else:
            logger.warning('unknown section type ' + section[0])

    return body_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/input/'):
        site = 'Input'
        path = split_url.path.replace('/input/', '/')
    else:
        site = site_json['site']
        path = split_url.path
    #graph_url = 'https://graph.bustle.com/?variables=%7B%22site%22%3A%22{}%22%2C%22path%22%3A%22{}%22%2C%22includeRelated%22%3Atrue%2C%22mosaicCardFeedLimit%22%3A8%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22a30f582ff45b31cdc13289410e3f43389417573d3911861db93b05aebe2a62f4%22%7D%7D&_client={}&_version=78ec64f'.format(site_json['site'].upper(), quote_plus(split_url.path), site_json['site'])
    graph_url = 'https://graph.bustle.com/?variables=%7B%22site%22%3A%22{}%22%2C%22path%22%3A%22{}%22%2C%22includeRelated%22%3Atrue%2C%22first%22%3A4%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22d4346fd59a4a49b0a7eee35f98bce511a9057f0158d3c1ec1176f736240743e6%22%7D%7D&_client={}&_version=a50ab3215'.format(site.upper(), quote_plus(path), site)
    # print(graph_url)
    graph_json = utils.get_url_json(graph_url)
    if not graph_json:
        logger.debug('graphql unsuccessful, extracting data from ' + url)
        article_html = utils.get_url_html(url)
        if not article_html:
            return None
        soup = BeautifulSoup(article_html, 'html.parser')
        el = soup.find('script', id='__INITIAL_STATE__')
        if not el:
            logger.warning('unable to find __INITIAL_STATE__ in ' + url)
            return None
        graph_json = json.loads(el.string)

    article_json = graph_json['data']['site']['contentByPath']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
        #utils.write_file(graph_json, './debug/content.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    tz = pytz.timezone('America/New_york')
    dt = datetime.fromtimestamp(article_json['firstPublishedAt'] / 1000)
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = utils.format_display_date(dt_utc)

    dt = datetime.fromtimestamp(article_json['publishedAt'] / 1000)
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    item['authors'] = [{"name": x['node']['name']} for x in article_json['authorConnection']['edges']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('categoryConnection'):
        item['tags'] += [x['name'] for x in article_json['categoryConnection']['nodes']]
    if article_json.get('tags'):
        for tag in article_json['tags']:
            if tag['slug'].casefold() in (name.casefold() for name in item['tags']):
                continue
            item['tags'].append(tag['slug'])

    if article_json.get('metaImage'):
        item['image'] = article_json['metaImage']['url']
    elif article_json.get('header'):
        if article_json['header']['card'].get('image'):
            item['image'] = article_json['header']['card']['image']['url']
        elif article_json['header']['card'].get('video'):
            item['image'] = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(
                article_json['header']['card']['video']['low']['url']))
    elif article_json.get('teaser'):
        if article_json['teaser'].get('image'):
            item['image'] = article_json['teaser']['image']['url']
        elif article_json['teaser'].get('video'):
            item['image'] = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(
                article_json['teaser']['video']['low']['url']))

    item['summary'] = article_json['description']

    item['content_html'] = ''
    if article_json.get('header'):
        item['content_html'] += render_card(article_json['header']['card'])

    if article_json.get('intro'):
        item['content_html'] += render_body(article_json['intro'], article_json['introZones'])

    if article_json.get('body'):
        item['content_html'] += render_body(article_json['body'], article_json['bodyZones'])

    if article_json.get('list'):
        for i, card in enumerate(article_json['list']):
            if article_json['listStyle'] == 'number':
                item['content_html'] += render_card(card['card'], i + 1)
            else:
                item['content_html'] += render_card(card['card'])

    if article_json.get('cardZones'):
        for card in article_json['cardZones']:
            item['content_html'] += render_card(card['card'])

    if article_json.get('outro'):
        item['content_html'] += render_body(article_json['outro'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
