import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def find_elements(el_name, el_json, el_ret):
    for i in range(0, len(el_json)):
        if isinstance(el_json[i], str):
            if el_json[i] == el_name:
                el_ret.append(el_json)
        elif isinstance(el_json[i], list):
            find_elements(el_name, el_json[i], el_ret)
    return


def get_caption(props, credit_only=False):
    captions = []
    if not credit_only:
        if props.get('dangerousCaption'):
            m = re.search(r'^<p>(.*)</p>\s*$', props['dangerousCaption'], flags=re.S)
            if m:
                captions.append(m.group(1))
            else:
                captions.append(props['dangerousCaption'])
        elif props.get('caption'):
            captions.append(props['caption'])

    if props.get('dangerousCredit'):
        captions.append(props['dangerousCredit'])
    elif props.get('credit'):
        captions.append(props['credit'])

    return ' | '.join(captions)


def get_image_src(image, width=1200):
    sources = []
    if image.get('sources'):
        for key, val in image['sources'].items():
            if val.get('aspectRatio') and val['aspectRatio'] == '1:1':
                continue
            sources.append(val)
    elif image.get('segmentedSources'):
        for key, val in image['segmentedSources'].items():
            for src in val:
                sources.append(src)
    src = utils.closest_dict(sources, 'width', width)
    return src['url']


def add_image(props, width=1000, caption='', credit_only=False):
    if props.get('image'):
        image = props['image']
    else:
        image = props
    img_src = get_image_src(image, width)
    if not caption:
        caption = get_caption(props, credit_only)
    return utils.add_image(img_src, caption)


def add_video(props, width=960):
    if props.get('image'):
        image = props['image']
    else:
        image = props
    sources = []
    for key, val in image['sources'].items():
        sources.append(val)
    src = utils.closest_dict(sources, 'width', 640)
    caption = get_caption(props)
    if '/clips/' in src['url']:
        # Gifs are often available for clips with width <=640
        gif = src['url'].replace('.mp4', '.gif')
        if utils.url_exists(gif):
            return utils.add_image(gif, caption)
    src = utils.closest_dict(sources, 'width', width)
    poster = '{}/image?url={}&width={}'.format(config.server, quote_plus(src['url']), width)
    return utils.add_video(src['url'], 'video/mp4', poster, caption)


def add_product(props):
    content_html = '<table style="width:100%"><tr>'
    if props.get('image'):
        content_html += '<td style="width:128px;"><img src="{}" style="width:128px;"/></td>'.format(props['image']['sources']['sm']['url'])
    if props.get('dangerousHed'):
        content_html += '<td style="vertical-align:top;"><h4 style="margin-top:0; margin-bottom:0.5em;">{}</h4>'.format(props['dangerousHed'])
    if props.get('dangerousDek'):
        content_html += '<div>{}</div>'.format(props['dangerousDek'])
    if props.get('multipleOffers'):
        content_html += '<ul>'
        for offer in props['multipleOffers']:
            content_html += '<li><a href="{}">'.format(offer['offerUrl'])
            if offer.get('price'):
                content_html += '{} at '.format(offer['price'])
            content_html += offer['sellerName'] + '</a></li>'
        content_html += '</ul>'
    content_html += '</td></tr></table>'
    return content_html


def format_body(body_json):
    #print(body_json[0])
    if body_json[0] == 'ad' or body_json[0] == 'native-ad' or body_json[0] == 'cm-unit' or body_json[0] == 'inline-newsletter':
        return ''

    start_tag = '<{}>'.format(body_json[0])
    end_tag = '</{}>'.format(body_json[0])

    if body_json[0] == 'blockquote':
        start_tag = '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">'
    elif body_json[0] == 'inline-embed':
        if body_json[1]['type'] == 'image':
            return add_image(body_json[1]['props'])
        elif body_json[1]['type'] == 'gallery':
            caption = '<a href="{}"><b>View Gallery</b></a>: {}'.format(body_json[1]['props']['url'], body_json[1]['props']['dangerousHed'])
            return add_image(body_json[1]['props']['tout'], caption=caption)
        elif body_json[1]['type'] == 'instagram':
            return utils.add_embed(body_json[1]['props']['url'])
        elif body_json[1]['type'] == 'clip':
            return add_video(body_json[1]['props'])
        elif body_json[1]['type'] == 'video':
            if 'youtube' in body_json[1]['props']['url']:
                return utils.add_embed(body_json[1]['props']['url'])
            else:
                logger.warning('unhandled inline-embed video ' + body_json[1]['props']['url'])
        elif body_json[1]['type'] == 'cneembed':
            video_src = ''
            m = re.search(r'https://player\.cnevids\.com/script/(video|playlist)/(\w+)\.js', body_json[1]['props']['scriptUrl'])
            if m:
                if m.group(1) == 'video':
                    video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId=' + m.group(2))
                    if video_json:
                        # Order of preference
                        for video_type in ['application/x-mpegURL', 'video/mp4', 'video/webm']:
                            for it in video_json['video']['sources']:
                                if it['type'] == video_type:
                                    video_src = it['src']
                                    break
                            if video_src:
                                break
                elif m.group(1) == 'playlist':
                    logger.debug('skipping cne video playlist https://player.cnevids.com/embed-api.json?playlistId=' + m.group(2))
                    return ''
            if video_src:
                return utils.add_video(video_src, video_type, video_json['video']['poster_frame'], video_json['video']['title'])
        elif body_json[1]['type'] == 'cneaudio':
            script = utils.get_url_html(body_json[1]['props']['scriptUrl'])
            if script:
                m = re.search(r'var varInit[^\{]+(\{.*?\});', script)
                if m:
                    # print(m.group(1).replace('\\"', '"'))
                    audio_json = json.loads(m.group(1).replace('\\"', '"'))
                    audio = audio_json['audios'][0]
                    return utils.add_audio(utils.find_redirect_url(audio['files'][0]), audio['image']['patternUrl'].replace('h_HEIGHT', 'h_512').replace('w_WIDTH', 'w_512'), audio['title'], '', audio_json['title'], '', utils.format_display_date(datetime.fromisoformat(audio['pubDate']), False), audio['duration'])
        elif body_json[1]['type'] == 'firework':
            firework_api = 'https://fireworkapi1.com/embed/v2/playlists/{}/feeds?page_size=10'.format(body_json[1]['ref'])
            firework_json = utils.post_url(firework_api)
            if firework_json:
                # utils.write_file(firework_json, './debug/firework.json')
                content_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for i in range(3):
                    video_json = firework_json['feed_items'][i]['video']
                    poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(video_json['thumbnail_url']))
                    caption = '<a href="{}">{}</a>'.format(video_json['web_share_url'], video_json['caption'])
                    content_html += '<div style="flex:1; min-width:240px;">'
                    content_html += utils.add_video(video_json['video_sources'][0]['src'], video_json['video_sources'][0]['type'], poster, caption)
                    content_html += '</div>'
                content_html += '</div>'
                return content_html
            else:
                logger.warning('failed to get firwork api ' + firework_api)
                return ''
        elif body_json[1]['type'] == 'iframe' or body_json[1]['type'] == 'twitter':
            return utils.add_embed(body_json[1]['props']['url'])
        elif body_json[1]['type'] == 'product':
            return add_product(body_json[1]['props'])
        elif body_json[1]['type'] == 'review':
            return '<table style="width:100%"><tr><td style="width:128px;"><img src="{}" style="width:128px;"/></td><td style="vertical-align:top;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="https://www.pitchfork.com{}">{}</a></h4><small>{}</small><br/><br/><a href="https://www.pitchfork.com{}">{}</a></td></tr></table>'.format(body_json[1]['props']['image']['sources']['sm']['url'], body_json[1]['props']['url'], body_json[1]['props']['dangerousHed'], body_json[1]['props']['artistName'], body_json[1]['props']['url'], body_json[1]['props']['buttonTextContent'])
        elif body_json[1]['type'] == 'justwatch':
            return utils.add_embed(body_json[1]['props']['url'])
        elif body_json[1]['type'] == 'pullquoteContent':
            start_tag = ''
            end_tag = ''
        elif body_json[1]['type'] == 'pullquoteCredit':
            start_tag = '<cite>'
            end_tag = '</cite>'
        elif body_json[1]['type'] == 'callout:button-group':
            start_tag = ''
            end_tag = ''
        elif body_json[1]['type'] == 'callout:align-center':
            start_tag = '<div style="text-align:center;">'
            end_tag = '</div>'
        elif re.search(r'callout:(dropcap|feature-default|feature-large|feature-medium|group-\d+|lead-in-text|pullquote)', body_json[1]['type']) or body_json[1]['type'] == 'callout:':
            # skip these but process the children
            start_tag = ''
            end_tag = ''
        elif body_json[1]['type'] == 'callout:anchor' and len(body_json) > 2:
            start_tag = ''
            end_tag = ''
        elif re.search(r'callout:(anchor|inset-left|inset-right|sidebar)', body_json[1]['type']) or body_json[1]['type'] == 'cneinterlude':
            # skip these entirely
            return ''
        elif body_json[1]['type'] == 'article':
            # skip related articles
            return ''
        else:
            logger.warning('unhandled inline-embed type ' + body_json[1]['type'])

    lead_in = False
    dropcap = False
    content_html = start_tag
    for block in body_json[1:]:
        if isinstance(block, dict) and start_tag:
            attrs = []
            for key, val in block.items():
                if key == 'class':
                    if 'has-dropcap' in val:
                        dropcap = True
                    if 'heading' in val:
                        m = re.search(r'heading-(h\d)', val)
                        if m:
                            n = len(start_tag)
                            content_html = content_html[:-n] + '<{}>'.format(m.group(1))
                            end_tag = '</{}>'.format(m.group(1))
                        else:
                            if not dropcap:
                                logger.warning('unknown heading level ' + val)
                    if 'paywall' in val:
                        continue
                    if 'lead-in-text-callout' in val:
                        lead_in = True
                        continue
                elif key == 'attributes':
                    for k, v in val.items():
                        attrs.append('{}="{}"'.format(k, v))
                    continue
                attrs.append('{}="{}"'.format(key, val))
            if attrs:
                content_html = content_html[:-1] + ' ' + ' '.join(attrs) + '>'
        elif isinstance(block, list):
            content_html += format_body(block)
        elif isinstance(block, str):
            if lead_in:
                content_html += block.upper()
            else:
                content_html += block

    if dropcap:
        content_html = re.sub(r'^(<[^>]+>)(\w)', r'\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>', content_html) + '<span style="clear:left;">&nbsp;</span>'

    content_html += end_tag

    if body_json[0] == 'inline-embed':
        if body_json[1]['type'] == 'callout:pullquote':
            m = re.search(r'<cite[^>]*>(.*?)</cite>', content_html)
            if m:
                content_html = utils.add_pullquote(content_html.replace(m.group(0), ''), m.group(1))
            else:
                content_html = utils.add_pullquote(content_html)
        elif body_json[1]['type'] == 'callout:button-group':
            soup = BeautifulSoup(content_html, 'html.parser')
            el = soup.find('a')
            if el:
                if el.get('data-offer-url'):
                    link = el['data-offer-url']
                else:
                    link = el['href']
                content_html = '<div><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; text-transform:uppercase; border:1px solid rgb(5, 125, 188);">{}</span></a></div>'.format(link, el.get_text())
            else:
                logger.warning('unhandled callout:button-group')

    return content_html


def get_content(url, args, site_json, save_debug=False):
    article_json = None
    clean_url = utils.clean_url(url)
    if not '/www.newyorker.com/' in clean_url:
        json_url = clean_url + '?format=json'
        article_json = utils.get_url_json(json_url)
    if not article_json:
        page_html = utils.get_url_html(clean_url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('script', string=re.compile(r'window\.__PRELOADED_STATE__'))
        if not el:
            logger.warning('unable to find PRELOADED_STATE in ' + clean_url)
            return None
        i = el.string.find('{')
        j = el.string.rfind('}') + 1
        preload_json = json.loads(el.string[i:j])
        article_json = preload_json['transformed']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['coreDataLayer']['content']['contentId']
    item['url'] = article_json['coreDataLayer']['page']['canonical']
    item['title'] = article_json['coreDataLayer']['content']['contentTitle']

    dt = datetime.fromisoformat(article_json['coreDataLayer']['content']['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['coreDataLayer']['content']['modifiedDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if article_json.get('article') and article_json['article']['headerProps'].get('contributors'):
        for key, val in article_json['article']['headerProps']['contributors'].items():
            for it in val['items']:
                if key == 'author':
                    item['authors'].append({"name": it['name']})
                else:
                    item['authors'].append({"name": '{} ({})'.format(it['name'], key)})
    elif article_json['coreDataLayer']['content'].get('authorNames'):
        item['authors'].append({"name": article_json['coreDataLayer']['content']['authorNames']})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    omit_tags = []
    if article_json['coreDataLayer']['content'].get('functionalTags'):
        omit_tags = article_json['coreDataLayer']['content']['functionalTags'].lower().split('|')
    if article_json['coreDataLayer']['content'].get('tags'):
        for tag in article_json['coreDataLayer']['content']['tags'].split('|'):
            if tag not in omit_tags:
                item['tags'].append(tag)
    if not item.get('tags'):
        del item['tags']

    item['image'] = article_json['head.og.image']
    item['summary'] = article_json['head.description']
    item['content_html'] = ''

    if article_json.get(article_json['head.pageType']):
        page_type = article_json['head.pageType']
    elif article_json.get(article_json['head.og.type']):
        page_type = article_json['head.og.type']
    else:
        logger.warning('unknown page type for ' + item['url'])
        return None
    body_json = article_json[page_type].get('body')

    # if article_json['head.pageType'] == article_json['head.og.type']:
    #     page_type = article_json['head.og.type']
    # else:
    #     if article_json.get('head.pageType'):
    #         page_type =
    #     if article_json['head.pageType'] in item['url']:
    #         page_type = article_json['head.pageType']
    #     elif article_json['head.og.type'] in item['url']:
    #         page_type = article_json['head.og.type']
    #     else:
    #         logger.warning('unknown page type for ' + item['url'])

    if article_json[page_type].get('headerProps'):
        if article_json[page_type]['headerProps'].get('dangerousDek'):
            item['content_html'] += '<p><em>{}</em></p>'.format(article_json[page_type]['headerProps']['dangerousDek'])
        if article_json[page_type]['headerProps'].get('lede'):
            lede = article_json[page_type]['headerProps']['lede']
            if lede.get('contentType') == 'photo':
                item['content_html'] += add_image(lede)
            elif lede.get('contentType') == 'clip':
                item['content_html'] += add_video(lede)
            elif lede.get('metadata') and lede['metadata'].get('contentType') == 'cnevideo':
                video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId=' + lede['cneId'])
                if video_json:
                    for it in video_json['video']['sources']:
                        if it['type'].find('mp4') > 0:
                            item['content_html'] += utils.add_video(it['src'], it['type'], video_json['video']['poster_frame'], video_json['video']['title'])
    elif 'image' in item:
        if '/cartoons/' not in item['url']:
            item['content_html'] += utils.add_image(item['image'])

    if page_type == 'review':
        item['content_html'] += '<h3>Rating: {}/{}</h3><p><em>PROS:</em> {}</p><p><em>CONS:</em> {}</p><div>&nbsp;</div><hr/><div>&nbsp;</div>'.format(
            article_json['review']['rating'], article_json['review']['bestRating'], article_json['review']['pros'],
            article_json['review']['cons'])

    if body_json:
        item['content_html'] += format_body(body_json)

    if page_type == 'gallery':
        for it in article_json[page_type]['items']:
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            if it.get('image'):
                item['content_html'] += add_image(it['image'], credit_only=True)
            if it.get('dangerousHed'):
                item['content_html'] += '<h3>{}</h3>'.format(it['dangerousHed'])
            if it.get('brand') and it.get('name'):
                item['content_html'] += '<h4>{} {}</h4>'.format(it['brand'], it['name'])
            elif it.get('name'):
                item['content_html'] += '<h4>{}</h4>'.format(it['name'])
            if it.get('dek'):
                item['content_html'] += format_body(it['dek'])
            if it.get('offers'):
                item['content_html'] += '<ul>'
                for offer in it['offers']:
                    item['content_html'] += '<li><a href="{}">'.format(offer['offerUrl'])
                    if offer.get('price'):
                        item['content_html'] += '{} at '.format(offer['price'])
                    item['content_html'] += '{}</a></li>'.format(offer['sellerName'])
                item['content_html'] += '</ul>'

    split_url = urlsplit(url)
    item['content_html'] = item['content_html'].replace('<a href="/', '<a href="{}://{}/'.format(split_url.scheme, split_url.netloc))
    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
