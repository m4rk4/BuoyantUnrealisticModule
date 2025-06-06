import base64, certifi, json, math, pytz, random, re, requests, STPyV8, time
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

# TODO
# slideshowembed: https://www.wsj.com/arts-culture/fine-art/ann-lowe-american-couturier-review-winterthur-jacqueline-kennedy-wedding-c0ef859d
# Fix - 2 leads: https://www.wsj.com/tech/personal-tech/chatgpt-can-now-chat-aloud-with-you-and-yes-it-sounds-pretty-much-human-3be39840


def get_stock_price(symbol):
    logger.debug('getting stock price for ' + symbol)
    # token = api_json['endpoints']['michelangeloToken']
    token = 'c1b7ca756343461b86565b61bbd2ac6f'
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "dylan2010.entitlementtoken": token,
        "priority": "u=1, i",
        "referrer": "https://www.barrons.com/",
        "sec-ch-ua": "\"Chromium\";v=\"130\", \"Microsoft Edge\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    api_url = 'https://api.barrons.com/api/dylan/quotes/v2/comp/quoteByDialect?ckey={}&MaxInstrumentMatches=1&needed=CompositeTrading%7CBluegrassChannels%7CCurrencySpecific&dialect=charting&id={}'.format(token[:10], quote_plus(symbol))
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    utils.write_file(api_json, './debug/stock.json')
    instrument = api_json['InstrumentResponses'][0]['Matches'][0]['Instrument']
    trading = api_json['InstrumentResponses'][0]['Matches'][0]['CompositeTrading']
    pct = (trading['Last']['Price']['Value'] - trading['Open']['Value']) / trading['Open']['Value'] * 100
    if pct < 0:
        color = 'red'
        arrow = '▼'
    else:
        color = 'green'
        arrow = '▲'
    stock_html = '<span style="color:{}; text-decoration:none;">{} ${:,.2f} {} {:,.2f}%</span>'.format(color, instrument['Ticker'], trading['Last']['Price']['Value'], arrow, pct)
    return stock_html


def render_contents(contents, netloc, article_links, image_link=None):
    content_html = ''
    if isinstance(contents, dict):
        contents_list = []
        contents_list.append(contents)
    else:
        contents_list = contents
    for content in contents_list:
        if not content.get('type'):
            if content.get('upstreamType'):
                if content['upstreamType'] == 'link':
                    content_html += '<a href="{}" target="_blank">'.format(content['decorationMetadata']['uri'])
                    if content.get('text'):
                        content_html += content['text']
                    elif content.get('nestedTextAndDecorations'):
                        content_html += render_contents(content['nestedTextAndDecorations'], netloc, article_links)
                    content_html += '</a>'
                elif content['upstreamType'] == 'emphasis':
                    if content['decorationType'] == 'BOLD':
                        tag = 'strong'
                    else:
                        tag = 'em'
                    content_html += '<{}>'.format(tag)
                    if content.get('text'):
                        content_html += content['text']
                    elif content.get('nestedTextAndDecorations'):
                        content_html += render_contents(content['nestedTextAndDecorations'], netloc, article_links)
                    content_html += '</{}>'.format(tag)
                elif content['upstreamType'] == 'break':
                    # TODO: ignore content['upstreamType'] == 'Break'
                    content_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
                elif content['upstreamType'] == 'company':
                    link = ''
                    if netloc == 'www.barrons.com':
                        link = 'https://www.barrons.com/market-data/'
                        if content['decorationMetadata']['chartingSymbol'].startswith('STOCK'):
                            link += 'stocks/'
                        elif content['decorationMetadata']['chartingSymbol'].startswith('FUTURE'):
                            link += 'futures/'
                        link += content['decorationMetadata']['instrumentResult']['ticker']
                    elif netloc == 'www.marketwatch.com':
                        link = 'https://www.barrons.com/investing/'
                        if content['decorationMetadata']['chartingSymbol'].startswith('STOCK'):
                            link += 'stock/'
                        elif content['decorationMetadata']['chartingSymbol'].startswith('FUTURE'):
                            link += 'future/'
                        link += content['decorationMetadata']['instrumentResult']['ticker']
                    elif netloc == 'www.wsj.com':
                        if '/US/' in content['decorationMetadata']['chartingSymbol']:
                            link = 'https://www.wsj.com/market-data/quotes/' + content['decorationMetadata']['instrumentResult']['ticker']
                        else:
                            link = 'https://www.wsj.com/market-data/quotes/' + content['decorationMetadata']['chartingSymbol'].replace('STOCK/', '')
                    if not link:
                        logger.warning('unknown company link ' + content['decorationMetadata']['chartingSymbol'])
                    content_html += '<a href="{}" target="_blank">{}</a>'.format(link, content['text'])
                    stock_html = get_stock_price(content['decorationMetadata']['chartingSymbol'])
                    if stock_html:
                        content_html += ' (' + stock_html + ')'
                elif content['upstreamType'] == 'instrument':
                    link = ''
                    if netloc == 'www.barrons.com':
                        link = 'https://www.barrons.com/market-data/'
                        if content['decorationMetadata']['chartingSymbol'].startswith('INDEX'):
                            link += 'indexes/'
                        elif content['decorationMetadata']['instrumentType'] == 'exchangetradedfund':
                            link += 'funds/'
                        else:
                            link += 'stocks/'
                        link += content['decorationMetadata']['ticker']
                    elif netloc == 'www.marketwatch.com':
                        link = 'https://www.marketwatch.com/investing/'
                        if content['decorationMetadata']['chartingSymbol'].startswith('INDEX'):
                            link += 'indexes/'
                        elif content['decorationMetadata']['instrumentType'] == 'exchangetradedfund':
                            link += 'funds/'
                        else:
                            link += 'stocks/'
                        link += content['decorationMetadata']['ticker']
                    elif netloc == 'www.wsj.com':
                        paths = content['decorationMetadata']['chartingSymbol'].split('/')
                        link = 'https://www.wsj.com/market-data/quotes/{}/{}/{}'.format(paths[0], paths[1], content['decorationMetadata']['ticker'])
                    if not link:
                        logger.warning('unknown instrument link ' + content['decorationMetadata']['chartingSymbol'])
                    content_html += '<a href="{}" target="_blank">{}</a>'.format(link, content['text'])
                    stock_html = get_stock_price(content['decorationMetadata']['chartingSymbol'])
                    if stock_html:
                        content_html += ' (' + stock_html + ')'
                elif content['upstreamType'] == 'person':
                    # TODO: link
                    content_html += content['text']
                else:
                    logger.warning('unhandled upstreamType ' + content['upstreamType'])
            elif content.get('text'):
                content_html += content['text']
            else:
                logger.warning('unhandled content ' + str(content))
        elif content['type'] == 'paragraph':
            content_html += '<p>'
            if content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            content_html += '</p>'
        elif content['type'] == 'blockquote':
            quote = ''
            if content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                quote += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                quote += render_contents(content['content'], netloc, article_links)
            content_html += utils.add_blockquote(quote)
        elif content['type'] == 'headline':
            content_html += '<h2>'
            if content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            content_html += '</h2>'
        elif content['type'] == 'hed':
            if content.get('hed_type') == 'subhed' or content.get('hedType') == 'subhed':
                tag = 'h2'
            elif content.get('hed_type') == 'small-hed' or content.get('hedType') == 'small-hed':
                tag = 'h3'
            else:
                logger.warning('unknown hed type')
                tag = 'h3'
            content_html += '<{}>'.format(tag)
            if content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            content_html += '</{}>'.format(tag)
        elif content['type'] == 'list':
            if content.get('ordered'):
                tag = 'ol'
            else:
                tag = 'ul'
            content_html += '<{}>'.format(tag)
            if content.get('listContent'):
                content_html += render_contents(content['listContent'], netloc, article_links)
            elif content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            content_html += '</{}>'.format(tag)
        elif content['type'] == 'listitem':
            content_html += '<li>'
            if content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('textAndDecorations') and content['textAndDecorations'].get('nested'):
                content_html += render_contents(content['textAndDecorations']['nested'], netloc, article_links)
            elif content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            content_html += '</li>'
        elif content['type'] == 'phrase':
            if content.get('href'):
                content_html += '<a href="https://{}{}">{}</a>'.format(netloc, content['href'], content['text'])
            else:
                content_html += content['text']
        elif content['type'] == 'link':
            if content.get('content'):
                link_content = render_contents(content['content'], netloc, article_links)
            elif content.get('text'):
                link_content = content['text']
            else:
                link_content = ''
                logger.warning('unknown link content ' + str(content))
            link_uri = ''
            if not content.get('uri') and content.get('ref'):
                link = next((it for it in article_links['related'] if (it['type'] == 'link' and it['id'] == content['ref'])), None)
                if link:
                    link_uri = link['uri']
            else:
                link_uri = content['uri']
            if link_uri:
                content_html += '<a href="{}">{}</a>'.format(link_uri, link_content)
            else:
                logger.warning('unknown link uri')
                content_html += link_content
        elif content['type'] == 'emphasis':
            if content['emphasis'] == 'BOLD':
                tag = 'strong'
            elif content['emphasis'] == 'ITALIC':
                tag = 'em'
            else:
                tag = 'em'
            if content.get('content'):
                content_html += '<{0}>{1}</{0}>'.format(tag, render_contents(content['content'], netloc, article_links))
            elif content.get('text'):
                content_html += '<{0}>{1}</{0}>'.format(tag, content['text'])
        elif content['type'] == 'sub':
            if content.get('content'):
                content_html += '<sub>' + render_contents(content['content'], netloc, article_links) + '</sub>'
            elif content.get('text'):
                content_html += '<sub>{}</sub>'.format(content['text'])
        elif content['type'] == 'sup':
            if content.get('content'):
                content_html += '<sup>' + render_contents(content['content'], netloc, article_links) + '</sup>'
            elif content.get('text'):
                content_html += '<sup>{}</sup>'.format(content['text'])
        elif content['type'] == 'tagline':
            if content.get('content'):
                content_html +=  '<h5>' + render_contents(content['content'], netloc, article_links) + '</h5>'
        elif content['type'] == 'image':
            if content.get('ref') and (content['ref'].startswith('ai2html') or content['ref'].startswith('image_')):
                image = next((it for it in article_links['related'] if (it['type'] == 'image' and it['id'] == content['ref'])), None)
                if not image:
                    logger.warning('unknown image ref ' + str(content))
                    continue
            else:
                image = content
                
            if image.get('src') and image['src'].get('path'):
                img_src = image['src']['baseUrl'] + image['src']['path'] + '?width=1200&size=' + image['src']['size']
            elif image.get('src') and image['src'].get('params'):
                img_src = image['src']['params']['href']
            elif image.get('name') and image['name'].startswith('https'):
                img_src = image['name']
            elif image.get('properties') and image['properties'].get('location'):
                img_src = image['properties']['location']
            elif image.get('displayVariants'):
                img_src = image['displayVariants'][image['displayVariants']['default']]['url']
            elif image.get('alt_images'):
                it = utils.closest_dict(image['alt_images'], 'width', 1200)
                img_src = it['url']
            elif image.get('url'):
                img_src = image['url']
            else:
                img_src = ''
            if not img_src:
                logger.warning('unknown image src for ' + image['id'])
                continue

            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('credit'):
                captions.append(image['credit'])
            content_html += utils.add_image(img_src, ' | '.join(captions), link=image_link)
        elif content['type'] == 'video' or (content['type'] == 'inset' and content.get('videoData')):
            video_json = None
            if content.get('video_service_props') and content['video_service_props'].get('jsonLD'):
                video_json = content['video_service_props']['jsonLD']
            elif content.get('videoData'):
                video_json = content['videoData']['jsonLD']
            if video_json:
                captions = []
                if content.get('caption'):
                    captions.append(content['caption'])
                elif video_json.get('description'):
                    captions.append(video_json['description'])
                if content.get('credit'):
                    captions.append(content['credit'])
                if '.mp4' in video_json['contentUrl']:
                    content_html += utils.add_video(video_json['contentUrl'], 'video/mp4', video_json['thumbnailUrl'], ' | '.join(captions))
                else:
                    content_html += utils.add_video(video_json['contentUrl'], 'application/x-mpegURL', video_json['thumbnailUrl'], ' | '.join(captions))
            else:
                if content.get('guid'):
                    video_id = content['guid']
                elif content.get('name'):
                    video_id = content['name']
                elif content.get('properties') and content['properties'].get('bigtopheroid'):
                    video_id = content['properties']['bigtopheroid']
                else:
                    logger.warning('unknown video id')
                    continue
                video_item = get_content('https://www.wsj.com/video/' + video_id, {"embed": True}, {}, False)
                if video_item:
                    content_html += video_item['content_html']
                else:
                    logger.warning('unhandled video content')
        elif content['type'] == 'media' and ((content.get('media_type') and content['media_type'].lower() == 'audio') or (content.get('mediaType')  and content['mediaType'].lower() == 'audio')):
            audio_item = get_content('https://www.wsj.com/podcasts/' + content['name'], {"embed": True}, {}, False)
            if audio_item:
                content_html += audio_item['content_html']
            else:
                logger.warning('unhandled audio content')
        elif content['type'] == 'table':
            content_html += '<table>' + render_contents(content['content'], netloc, article_links) + '</table>'
        elif content['type'] == 'tr' or content['type'] == 'td':
            content_html += '<{0}>{1}</{0}>'.format(content['type'], render_contents(content['content'], netloc, article_links))
        elif content['type'] == 'Break':
            content_html += '<br/>'
        elif content['type'] == 'inset':
            if content.get('insetType'):
                inset_type = content['insetType']
            elif content.get('inset_type'):
                inset_type = content['inset_type']
            else:
                inset_type = ''
            if content.get('__typename'):
                if content['__typename'] == 'InsetArticleBody' and inset_type == 'bigtophero':
                    if content['properties']['dataType'] == 'Image':
                        captions = []
                        if content['properties'].get('imageCaption'):
                            captions.append(content['properties']['imageCaption'])
                        if content['properties'].get('imageCredit'):
                            captions.append(content['properties']['imageCredit'])
                        content_html += utils.add_image(content['properties']['urlLarge'], ' | '.join(captions))
                    elif content['properties']['dataType'] == 'AutoPlayVideoClip':
                        captions = []
                        if content['properties'].get('videoCaption'):
                            captions.append(content['properties']['videoCaption'])
                        if content['properties'].get('imageCaption'):
                            captions.append(content['properties']['imageCaption'])
                        if content['properties'].get('imageCredit'):
                            captions.append(content['properties']['imageCredit'])
                        content_html += utils.add_video(content['properties']['bigTopHeroVideoData']['videoContent']['jsonLD']['contentUrl'], 'video/mp4', content['properties']['bigTopHeroVideoData']['videoContent']['jsonLD']['thumbnailUrl'], ' | '.join(captions), use_videojs=True)
                    else:
                        logger.warning('unhandled InsetArticleBody bigtophero data type ' + content['properties']['dataType'])
                elif content['__typename'] == 'InsetArticleBody' and inset_type == 'pagebreak':
                    content_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
                elif content['__typename'] == 'InsetArticleBody' and inset_type == 'dynamic' and content['content']['subType'] == 'charts':
                    content_html += utils.add_image(utils.clean_url(content['content']['alt']['picture']['img']['src']), content['content']['alt']['text'], link=content['content']['alt']['render']['src'])
                elif content['__typename'] == 'SeriesNavigationInsetArticleBody':
                    inset_json = utils.get_url_json(content['url'])
                    if inset_json:
                        content_html += render_contents(inset_json['alt']['capi']['data']['attributes']['body'], netloc, inset_json['alt']['capi']['links'])
                elif content['__typename'] == 'OrigamiInsetArticleBody' and content['content'].get('strippedHTML'):
                    inset_soup = BeautifulSoup(content['content']['strippedHTML'], 'html.parser')
                    if inset_soup.find('video'):
                        video = inset_soup.find('video')
                        video_src = video.find('source', attrs={"type": "video/mp4"})
                        if video_src:
                            it = inset_soup.find(class_='origami-caption')
                            if it:
                                caption = it.decode_contents()
                            else:
                                caption = ''
                            content_html += utils.add_video(video_src['src'], video_src['type'], video.get('poster'), caption)
                        else:
                            logger.warning('unhandled OrigamiInsetArticleBody video')
                    elif len(inset_soup.select('div.origami-item > figure')) > 1:
                        gallery_images = []
                        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        for i, el in enumerate(inset_soup.find_all(class_='origami-item')):
                            img_src = utils.clean_url(el.figure.img['src'])
                            thumb = el.img['src']
                            it = el.find(class_='origami-caption')
                            if it:
                                caption = it.decode_contents()
                            else:
                                caption = ''
                            gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                            gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                        if i % 2 == 0:
                            gallery_html += '<div style="flex:1; min-width:360px;"></div>'
                        gallery_html += '</div>'
                        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                        content_html += '<h3><a href="{}" target="_blank">View photo gallery</a>'.format(gallery_url)
                        el = inset_soup.find(class_='origami-grouped-caption')
                        if el:
                            content_html += ': ' + el.decode_contents()
                        content_html += '</h3>' + gallery_html
                elif content['__typename'] == 'RichTextArticleBody':
                    inset_html = render_contents(content['richTextContent'], netloc, article_links)
                    if not re.search(r'SHARE YOUR THOUGHTS', inset_html):
                        content_html += inset_html
                elif content['__typename'] == 'TweetArticleBody':
                    content_html += utils.add_embed(content['properties']['tweetUrl'])
                elif content['__typename'] == 'DynamicInsetArticleBody':
                    print(content['id'])
                    if content['content'].get('subType') and (content['content']['subType'] == 'promo' or content['content']['subType'] == 'feedback-form'):
                        continue
                    elif content['content'].get('subType') and content['content']['subType'] == 'charts':
                        content_html += utils.add_image(utils.clean_url(content['content']['alt']['picture']['img']['src']), content['content']['alt']['text'], link=content['content']['alt']['render']['src'])
                    elif content['content'].get('subType') and content['content']['subType'] == 'ai2html':
                        img_src = utils.clean_url(content['content']['alt']['picture']['img']['src']).replace('fallback_classic', 'fallback_wide')
                        if content['content']['alt']['capi']['data']['attributes'].get('headline'):
                            caption = content['content']['alt']['capi']['data']['attributes']['headline']['text']
                        else:
                            caption = ''
                        link = 'https://pub-prod-djcs-dynamicinset-renderer.ohi.onservo.com/?url=' + content['properties']['url']
                        content_html += utils.add_image(img_src, caption, link=link)
                    elif content['content'].get('subType') and content['content']['subType'] == 'tap-unmute':
                        for it in content['content']['serverSide']['data']['data']['items']:
                            if it['type'] == 'video':
                                captions = []
                                if it['data'].get('caption'):
                                    captions.append(it['data']['caption'])
                                if it['data'].get('credit'):
                                    captions.append(it['data']['credit'])
                                content_html += utils.add_video(it['data']['media'], 'video/mp4', it['data']['thumbnail'], ' | '.join(captions), use_videojs=True)
                            else:
                                logger.warning('unhandled DynamicInsetArticleBody tap-unmute id ' + content['id'])
                    elif content['content'].get('subType') and content['content']['subType'] == 'parallax-gallery':
                        inset_json = utils.get_url_json(content['url'])
                        if inset_json:
                            gallery_images = []
                            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                            for i, it in enumerate(inset_json['serverside']['data']['data']['items']):
                                if it['type'] == 'image':
                                    img_src = it['data']['media']
                                    thumb = img_src + '?width=640'
                                elif it['type'] == 'video':
                                    img_src = it['data']['media']
                                    thumb = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(it['data']['thumbnailURL']))
                                if it['data'].get('mediaCredit'):
                                    caption = it['data']['mediaCredit']
                                else:
                                    caption = ''
                                if it['data'].get('mediaBody'):
                                    desc = it['data']['mediaBody']
                                else:
                                    desc = ''
                                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
                                gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
                            if i % 2 == 0:
                                gallery_html += '<div style="flex:1; min-width:360px;"></div>'
                            gallery_html += '</div>'
                            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                            content_html += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
                    elif content['content'].get('strippedHTML') and '<iframe' in content['content']['strippedHTML']:
                        m = re.search(r'src="([^"]+)"', content['content']['strippedHTML'])
                        content_html += utils.add_embed(m.group(1))
                    elif content['content'].get('subType') == None and content['content'].get('alt') == None:
                        link = 'https://pub-prod-djcs-dynamicinset-renderer.ohi.onservo.com/?url=' + content['properties']['url']
                        content_html += utils.add_image(config.server + '/screenshot?cropbbox=1&url=' + quote_plus(link), link=link)
                    else:
                        content_html += render_contents(content['content']['alt']['capi']['data']['attributes']['body'], netloc, content['content']['alt']['capi']['links'])
                elif content['__typename'] == 'NewsletterInsetArticleBody':
                    continue
                else:
                    logger.warning('unhandled inset __typename ' + content['__typename'])
            elif inset_type == 'ai2html' and content.get('content'):
                content_html += render_contents(content['content'], netloc, article_links)
            elif inset_type == 'bigtophero' and content['properties']['datatype'] == 'Image':
                captions = []
                if content['properties'].get('imagecaption'):
                    captions.append(content['properties']['imagecaption'])
                if content['properties'].get('imagecredit'):
                    captions.append(content['properties']['imagecredit'])
                content_html += utils.add_image(content['properties']['urllarge'], ' | '.join(captions))
            elif inset_type == 'slideshow':
                content_html += render_contents(content['content'], netloc, article_links)
            elif inset_type == 'videobyguid':
                video_item = get_content('https://www.wsj.com/video/' + content['properties']['videoguid'], {"embed": True}, {}, False)
                if video_item:
                    content_html += video_item['content_html']
                else:
                    logger.warning('unhandled videobyguid content')
            elif inset_type == 'youtube':
                content_html += utils.add_embed('https://www.youtube.com/' + content['properties']['url'])
            elif inset_type == 'tweet':
                content_html += utils.add_embed(content['properties']['url'])
            elif inset_type == 'pagebreak':
                content_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            elif inset_type == 'pullquote':
                author = ''
                for i, it in enumerate(content['content']):
                    if it['type'] == 'tagline':
                        if it.get('content'):
                            author = render_contents(it['content'], netloc, article_links)
                        del content['content'][i]
                text = render_contents(content['content'], netloc, article_links)
                content_html += utils.add_pullquote(text, author)
            elif inset_type == 'advisortake':
                if content.get('content'):
                    content_html +=  render_contents(content['content'], netloc, article_links)
            elif inset_type == 'dynamic':
                inset_html = ''
                link = 'https://pub-prod-djcs-dynamicinset-renderer.ohi.onservo.com/?url=' + content['properties']['url']
                if content.get('chartData') and content['chartData'].get('src'):
                    inset_html += utils.add_image(content['chartData']['src'], link=link)
                elif content.get('dynamic_inset_properties') and content['dynamic_inset_properties'].get('resolvedInset'):
                    if content['dynamic_inset_properties']['resolvedInset'].get('subType'):
                        if content['dynamic_inset_properties']['resolvedInset']['subType'] == 'data-table':
                            soup = BeautifulSoup(content['dynamic_inset_properties']['resolvedInset']['strippedHTML'], 'html.parser')
                            table = soup.find('table')
                            it = soup.find('div', class_='wsj-data-table')
                            if it:
                                it['style'] = 'width:90%; margin-left:auto; margin-right:auto;'
                                table['style'] = 'width:100%; border-collapse:collapse; border-bottom:1px solid black;'
                            else:
                                table['style'] = 'width:90%; margin-left:auto; margin-right:auto; width:100%; border-collapse:collapse; border-bottom:1px solid black;'
                            for i, it in enumerate(soup.find_all('tr')):
                                if i == 0:
                                    it['style'] = 'border-top:1px solid black; background-color:#ccc;'
                                elif i % 2 == 0:
                                    it['style'] = 'background-color:#ccc;'
                            for it in soup.find_all('p'):
                                it['style'] = 'font-size:0.8em;'
                            inset_html += str(soup)
                        elif content['dynamic_inset_properties']['resolvedInset']['subType'] == 'origami':
                            inset_json = utils.get_url_json(content['properties']['url'])
                            if inset_json:
                                if inset_json.get('alt') and inset_json['alt'].get('capi') and inset_json['alt']['capi'].get('links') and inset_json['alt']['capi']['links'].get('related'):
                                    inset_html += render_contents(inset_json['alt']['capi']['links']['related'], netloc, article_links)
                        elif content['dynamic_inset_properties']['resolvedInset']['subType'] == 'parallax-gallery':
                            inset_json = utils.get_url_json(content['properties']['url'])
                            if inset_json:
                                inset_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                                for it in inset_json['serverside']['data']['data']['items']:
                                    inset_html += '<div style="flex:1; min-width:256px;">'
                                    if it['data'].get('mediaTitle'):
                                        inset_html += '<div style="text-align:center;"><b>{}</b></div>'.format(it['data']['mediaTitle'])
                                    if it['type'] == 'image':
                                        inset_html += '<div><a href="{0}"><img src="{0}" style="width:100%;"/></a></div>'.format(it['data']['media'])
                                    else:
                                        logger.warning('unhandled parallax-gallery item type ' + it['type'])
                                    if it['data'].get('mediaBody'):
                                        inset_html += re.sub(r'<(/?)p>', r'<\1div>', it['data']['mediaBody'])
                                    inset_html += '</div>'
                                inset_html += '</div>'
                        elif content['dynamic_inset_properties']['resolvedInset']['subType'] == 'seo-schema-books':
                            inset_json = None
                            for it in content['dynamic_inset_properties']['resolvedInset']['scripts']:
                                soup = BeautifulSoup(it, 'html.parser')
                                el = soup.find('script', id='seo-schema-script-tag')
                                if el:
                                    inset_json = json.loads(el.string)
                                    if inset_json['itemReviewed'].get('sameAs'):
                                        link = inset_json['itemReviewed']['sameAs']
                                    else:
                                        link = 'https://www.amazon.com/gp/search?index=books&tag=wsjopbks-20&field-isbn=' + inset_json['itemReviewed']['isbn']
                                    inset_html = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div>By {} ({})</div>'.format(link, inset_json['itemReviewed']['image'], link, inset_json['itemReviewed']['name'], inset_json['itemReviewed']['author']['name'], inset_json['itemReviewed']['publisher']['name'])
                                    inset_html += '<p>&bull; <a href="https://www.amazon.com/gp/search?index=books&tag=wsjopbks-20&field-isbn={0}">Find on Amazon</a><br/>&bull; <a href="https://www.barnesandnoble.com/s/{0}">Find on Barnes & Noble</a><br/>&bull; <a href="https://www.booksamillion.com/search?query={0}">Find on Books a Million</a><br/>&bull; <a href="https://bookshop.org/books?keywords={0}">Find on Bookshop</a></p></td></tr></table>'.format(inset_json['itemReviewed']['isbn'])
                                    break
                        elif content['dynamic_inset_properties']['resolvedInset']['subType'] == 'series-navigation' or content['dynamic_inset_properties']['resolvedInset']['subType'] == 'promo' or content['dynamic_inset_properties']['resolvedInset']['subType'] == 'feedback-form':
                            continue
                    elif content['dynamic_inset_properties']['resolvedInset'].get('strippedHTML'):
                        soup = BeautifulSoup(content['dynamic_inset_properties']['resolvedInset']['strippedHTML'], 'html.parser')
                        video = soup.find('video')
                        if video:
                            captions = []
                            it = soup.find(class_='bc-credit')
                            if it:
                                captions.append(it.get_text().strip())
                                it.decompose()
                            it = soup.find(class_='bc-caption')
                            if it:
                                captions.insert(0, it.get_text().strip())
                            inset_html += utils.add_video(video['src'], 'video/mp4', video.get('poster'), ' | '.join(captions))
                if not inset_html:
                    inset_json = utils.get_url_json(content['properties']['url'])
                    if inset_json:
                        if inset_json.get('alt') and inset_json['alt'].get('picture') and inset_json['alt']['picture'].get('img'):
                            inset_html += utils.add_image(inset_json['alt']['picture']['img']['src'], link=link)
                        if inset_json.get('alt') and inset_json['alt'].get('capi') and inset_json['alt']['capi'].get('links') and inset_json['alt']['capi']['links'].get('related'):
                            inset_html += render_contents(inset_json['alt']['capi']['links']['related'], netloc, article_links, image_link=link)
                if inset_html:
                    content_html += inset_html
                else:
                    logger.warning('unhandled dynamic inset')
                    content_html += '<blockquote><b><a href="{}">View dynamic inset content</a></b></blockquote>'.format(link)
            elif inset_type == 'richtext':
                text = render_contents(content['content'], netloc, article_links)
                if not re.search(r'>read more|>SHARE YOUR THOUGHTS|>Explore Buy Side|>new from', text, flags=re.I):
                    content_html += '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">' + text + '</blockquote>'
            elif inset_type == 'newsletterinset' or inset_type == 'relatedbyarticletype':
                pass
            elif content['type'] == 'inset' and inset_type == 'normal' and not content.get('content'):
                pass
            else:
                logger.warning('unhandled inset type ' + inset_type)
        else:
            logger.warning('unhandled content type ' + content['type'])
    return content_html


def find_signed_url():
    reddit_posts = []
    reddit_json = utils.get_url_json('https://www.reddit.com/user/wsj/submitted.json?sort=new')
    if reddit_json:
        for child in reddit_json['data']['children']:
            if child.get('data'):
                reddit_posts.append(child['data'])
    reddit_json = utils.get_url_json('https://www.reddit.com/user/wsj/comments.json?sort=new')
    if reddit_json:
        for child in reddit_json['data']['children']:
            if child.get('data'):
                reddit_posts.append(child['data'])
    if not reddit_json:
        return ''
    signed_url = ''
    reddit_posts = sorted(reddit_posts, key=lambda i: i['created_utc'], reverse=True)
    for post in reddit_posts:
        if post.get('url'):
            params = parse_qs(urlsplit(post['url']).query)
            if 'st' in params:
                signed_url = post['url']
        if not signed_url and post.get('link_url'):
            params = parse_qs(urlsplit(post['link_url']).query)
            if 'st' in params:
                signed_url = post['link_url']
        if not signed_url and post.get('url_overridden_by_dest'):
            params = parse_qs(urlsplit(post['url_overridden_by_dest']).query)
            if 'st' in params:
                signed_url = post['url_overridden_by_dest']
        if signed_url:
            break
    return signed_url


def decrypt_content(url, encryptedDocumentKey, encryptedDataHash):
    # Seems like if x-original-url has a valid paywall token for any article, then the given encryptedDocumentKey is decrypted
    # Tokes expire - some after about 7 days
    # WSJ links free articles from their reddit account:
    #     Search for links with "st=" in body (markdown), body_html, selftext (markdown), selftext_html, url, link_url, url_overridden_by_dest
    #     https://www.reddit.com/user/wsj/submitted.json?sort=new
    #     https://www.reddit.com/user/wsj/comments.json?sort=new
    # or look here: https://www.reddit.com/domain/wsj.com/.json
    # https://www.wsj.com/lifestyle/dog-owners-death-lessons-love-grief-53c77511?st=ycgues92xaxtr83
    # original_url = '/world/middle-east/israel-hamas-engage-in-some-of-fiercest-fighting-of-war-30edb859?st=mb6j2s8lus85b04'
    # original_url = 'https://www.wsj.com/world/europe/ukraine-withdraws-from-besieged-city-as-russia-advances-554644c0?st=g2h1gd2v9orwuhm'
    # original_url = '/world/middle-east/hamas-militants-had-detailed-maps-of-israeli-towns-military-bases-and-infiltration-routes-7fa62b05?st=i9kvxxh54grfkvu'
    # Adding mod=djemalertNEWS seems to bypass the need for a token
    # original_url = urlsplit(url).path + "?mod=djemalertNEWS"
    original_url = ''
    reddit_json = utils.get_url_json('https://www.reddit.com/user/wsj/comments.json?sort=new')
    if reddit_json:
        for comment in reddit_json['data']['children']:
            if comment['data'].get('body'):
                m = re.search(r'\((https://www.wsj.com/[^\)]+)\)', comment['data']['body'])
                if m:
                    print(m.group(1))
                    params = parse_qs(urlsplit(m.group(1)).query)
                    if params.get('st'):
                        original_url = m.group(1)
                        break

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"119\", \"Chromium\";v=\"119\", \"Not?A_Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "x-encrypted-document-key": encryptedDocumentKey,
        "x-original-host": "www.wsj.com",
        "x-original-referrer": "",
        "x-original-url": original_url
    }
    # Seems like using wsj.com works for other wsj sites as well (Barrons, etc.)
    client_json = utils.get_url_json('https://www.wsj.com/client', headers=headers)
    if not client_json:
        return None
    # print(client_json)
    if not client_json.get('documentKey'):
        logger.warning('unable to get documentKey')
        return None
    document_key = client_json['documentKey']
    key = base64.b64decode(document_key.encode())
    iv = base64.b64decode(encryptedDataHash['iv'].encode())
    content = base64.b64decode(encryptedDataHash['content'].encode())
    decryptor = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend()).decryptor()
    decrypted_content = decryptor.update(content) + decryptor.finalize()
    b64_content = base64.b64encode(decrypted_content).decode('utf-8')
    # TODO: convert this function to Python
    # TODO: untested using STPyV8
    with STPyV8.JSContext() as ctxt:
        decode_b64 = ctxt.eval('''
    ( (e) => {
        if ("string" !== typeof e)
            return null;
        if (0 === e.length)
            return "";
        const i = function() {
            let e = 0
              , i = ""
              , t = 0
              , l = 6;
            return {
                from: function(o) {
                    if ("string" !== typeof o || o.length % 4 !== 0)
                        throw new Error("Invalid base64 input.");
                    const n = o.match(/=+/);
                    n && (o = o.slice(0, n.index)),
                    e = 6 * o.length,
                    i = o,
                    t = 0,
                    l = 6
                },
                pop: function(o) {
                    const s = {"0": 52, "1": 53, "2": 54, "3": 55, "4": 56, "5": 57, "6": 58, "7": 59, "8": 60, "9": 61, "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7, "I": 8, "J": 9, "K": 10, "L": 11, "M": 12, "N": 13, "O": 14, "P": 15, "Q": 16, "R": 17, "S": 18, "T": 19, "U": 20, "V": 21, "W": 22, "X": 23, "Y": 24, "Z": 25, "a": 26, "b": 27, "c": 28, "d": 29, "e": 30, "f": 31, "g": 32, "h": 33, "i": 34, "j": 35, "k": 36, "l": 37, "m": 38, "n": 39, "o": 40, "p": 41, "q": 42, "r": 43, "s": 44, "t": 45, "u": 46, "v": 47, "w": 48, "x": 49, "y": 50, "z": 51, "+": 62, "/": 63};
                    if (e <= 0)
                        return null;
                    let n = 0
                      , r = s[i.charAt(t)];
                    if ("number" !== typeof r)
                        throw new Error("Encounter invalid base64 symbol.");
                    for (o = Math.min(o, e),
                    e -= o; o > 0; ) {
                        if (!(o >= l)) {
                            n |= (r & (1 << l) - 1) >> l - o,
                            l -= o;
                            break
                        }
                        n |= (r & (1 << l) - 1) << (o -= l),
                        t < i.length - 1 && (l = 6,
                        t += 1,
                        r = s[i.charAt(t)])
                    }
                    return n
                }
            }
        }();
        i.from(e);
        const t = [];
        let l, o, n = 2, a = 2, u = Math.pow(2, n) - 1, c = !0, d = 1 === i.pop(n) ? String.fromCharCode(i.pop(7)) : String.fromCharCode(i.pop(16)), v = d;
        for (; c && (t[++a] = d,
        c = !1),
        a >= u && (n += 1,
        u = Math.pow(2, n) - 1),
        l = i.pop(n),
        0 !== l; )
            1 === l ? (o = String.fromCharCode(i.pop(7)),
            c = !0) : 2 === l ? (o = String.fromCharCode(i.pop(16)),
            c = !0) : o = t[l] ? t[l] : d + d.charAt(0),
            t[++a] = d + o.charAt(0),
            v += o,
            d = o;
        return v
    }
        ''')
        decoded = decode_b64(b64_content)
    return decoded


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    path = re.sub(r'\.html', '', split_url.path, flags=re.I)
    paths = list(filter(None, path[1:].split('/')))
    if 'livecoverage' in paths:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if save_debug:
            utils.write_file(next_data, './debug/debug.json')

        page_props = next_data['props']['pageProps']

        item = {}
        if page_props.get('card'):
            card = page_props['card'][0]
            item['id'] = card['id']
            item['url'] = page_props['canonicalUrl']
            item['title'] = card['meta']['display']['hed']
            tz_loc = pytz.timezone(config.local_tz)
            dt_loc = datetime.fromtimestamp(card['publishedAt']/1000)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            dt_loc = datetime.fromtimestamp(card['updatedAt']/1000)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_modified'] = dt.isoformat()
            item['author'] = {"name": card['publishedBy']}
            item['content_html'] = '<div>Update: {}</div><div style="font-size:1.2em; font-weight:bold; padding-top:8px;"><a href="{}">{}</a></div><div style="padding-bottom:1em;">By {}</div>'.format(utils.format_display_date(dt), item['url'], item['title'], item['author']['name'])
            for it in card['data'].values():
                if it['type'] == 'text':
                    item['content_html'] += markdown(it['text'])
                elif it['type'] == 'image' or it['type'] == 'video':
                    item['content_html'] += render_contents([it], split_url.netloc, None)
                # if it['type'] == 'iframe':
                #     if 'dynamic-inset-iframer' in it['url']:
                else:
                    logger.warning('unhandled card data type {} in {}'.format(it['type'], item['url']))
            return item

        #item['id'] =
        item['url'] = page_props['canonicalUrl']
        item['title'] = page_props['headline']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(page_props['publishedAt'] / 1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt_loc = datetime.fromtimestamp(page_props['updatedAt'] / 1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

        article_json = next((it for it in page_props['seoSchema'] if it['@type'] == 'NewsArticle'), None)
        if article_json:
            item['author'] = {}
            authors = []
            if isinstance(article_json['author'], list):
                for it in article_json['author']:
                    if it.get('name'):
                        authors.append(it['name'])
            else:
                if article_json['author'].get('name'):
                    authors.append(article_json['author']['name'])
            if authors:
                item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
            else:
                if article_json.get('publisher') and article_json['publisher'].get('name'):
                    item['author']['name'] = article_json['publisher']['name']

            if article_json.get('image'):
                if isinstance(article_json['image'], list):
                    item['_image'] = article_json['image'][0]
                else:
                    item['_image'] = article_json['image']['url']

        if page_props.get('description'):
            item['summary'] = page_props['description']

        item['content_html'] = ''
        if page_props.get('dek'):
            item['content_html'] += '<p><em>{}</em></p>'.format(page_props['dek'])

        if page_props.get('featuredMedia') and page_props['featuredMedia'].get('data'):
            for it in page_props['featuredMedia']['data'].values():
                item['content_html'] += render_contents([it], split_url.netloc, None)

        if page_props.get('featuredContent') and page_props['featuredContent'].get('data'):
            for it in page_props['featuredContent']['data'].values():
                item['content_html'] += markdown(it['text'])

        article_json = next((it for it in page_props['seoSchema'] if it['@type'] == 'LiveBlogPosting'), None)
        if article_json:
            for post in article_json['liveBlogUpdate']:
                post_url = post['url'].replace('#card-', '/card/')
                post_item = get_content(post_url, args, site_json, False)
                item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>' + post_item['content_html']
        return item

    if 'video' in paths or 'podcasts' in paths:
        if 'podcasts' in paths:
            api_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=guid&query={}&fields=adZone,audioURL,audioURLPanoply,author,body,column,description,doctypeID,duration,episodeNumber,formattedCreationDate,guid,keywords,linkURL,name,omniPublishDate,omniVideoFormat,playbackSite,podcastName,podcastSubscribeLinks,podcastUrl,rootId,thumbnailImageManager,thumbnailList,titletag,type,wsj-section,wsj-subsection&snippet=true'.format(paths[-1])
        else:
            api_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=guid&fields=adCategory%2CadTagParams%2CadZone%2CadsAllowed%2CaspectRatio%2Cauthor%2CcaptionsVTT%2Ccatastrophic%2CchapterTimes%2Ccolumn%2Cdescription%2CdoctypeID%2Cduration%2Ceditor%2CemailURL%2CepisodeNumber%2CforceClosedCaptions%2Cformat%2CformattedCreationDate%2CgptCustParams%2Cguid%2Chls%2ChlsNoCaptions%2CisQAEvent%2Ciso8601CreationDate%2Ckeywords%2CkeywordsOmni%2ClinkRelativeURL%2ClinkShortURL%2ClinkURL%2CmediaLiveChannelId%2Cname%2ComniProgramName%2ComniPublishDate%2ComniVideoFormat%2Cprovider%2CrssURL%2CsecondsUntilStartTime%2CseriesName%2CshowName%2CsponsoredVideo%2Clang%2Cstate%2CsuppressAutoplay%2CthumbnailImageManager%2CthumbnailList%2CthumbstripURL%2CthumbstripVTTURL%2Ctitletag%2CtouchCastID%2Ctype%2Cvideo1264kMP4Url%2Cvideo174kMP4Url%2Cvideo1864kMP4Url%2Cvideo2564kMP4Url%2Cvideo320kMP4Url%2Cvideo664kMP4Url%2CvideoBestQualityWebmUrl%2CvideoMP4List%2CvideoStillURL%2Cwsj-section%2Cwsj-subsection%2Cfactiva-subjects%2Cfactiva-regions&count=1&query=' + paths[-1]
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        video_json = api_json['items'][0]
        if save_debug:
            utils.write_file(video_json, './debug/video.json')
        item = {}
        item['id'] = video_json['guid']
        item['url'] = video_json['linkURL']
        item['title'] = video_json['name']

        if video_json.get('iso8601CreationDate'):
            dt = datetime.fromisoformat(video_json['iso8601CreationDate'])
        elif video_json.get('formattedCreationDate'):
            tz_loc = pytz.timezone(config.local_tz)
            dt_loc = dateutil.parser.parse(video_json['formattedCreationDate'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        else:
            dt = None
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)

        if video_json.get('seriesName'):
            item['author'] = {
                "name": video_json['seriesName']
            }
        elif video_json.get('column'):
            item['author'] = {
                "name": video_json['column']
            }
        elif video_json.get('author'):
            item['author'] = {
                "name": video_json['author']
            }
        if item.get('author'):
            if video_json.get('podcastUrl'):
                item['author']['url'] = video_json['podcastUrl']
            item['authors'] = []
            item['authors'].append(item['author'])

        if video_json.get('keywords'):
            item['tags'] = video_json['keywords'].copy()

        if video_json.get('description'):
            item['summary'] = video_json['description']

        image = utils.closest_dict(video_json['thumbnailList'], 'width', 1200)
        if image:
            item['image'] = image['url']
        else:
            item['image'] = video_json['thumbnailManager']

        if video_json['type'] == 'video':
            if video_json.get('hls'):
                item['content_html'] = utils.add_video(video_json['hls'], 'application/x-mpegURL', item['image'], item['title'])
            elif video_json.get('videoMP4List'):
                video = utils.closest_dict(video_json['videoMP4List'], 'bitrate', 2000)
                if video:
                    item['content_html'] = utils.add_video(video['url'], 'video/mp4', item['image'], item['title'])

        elif video_json['type'] == 'audio':
            item['_audio'] = video_json['audioURL']
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], video_json['duration'], audio_type='audio/mpeg', use_video_js=True)

        if item.get('summary') and 'embed' not in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
            if video_json.get('body'):
                item['content_html'] += '<h2>Transcript:</h2>'
                for it in video_json['body']:
                    item['content_html'] += '<p>' + it + '</p>'
        return item

    if site_json['datadome'] == '':
        site_json['datadome'] = utils.get_datadome_cookie('https://www.barrons.com', 'D428D51E28968797BC27FB9153435D')
        utils.update_sites(url, site_json)
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "cookie": site_json['datadome'],
        "pragma": "no-cache",
        "upgrade-insecure-requests": "1"
    }
    api_url = site_json['articles_api'] + paths[-1]
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        site_json['datadome'] = utils.get_datadome_cookie('https://www.barrons.com', 'D428D51E28968797BC27FB9153435D')
        utils.update_sites(url, site_json)
        headers['cookie'] = site_json['datadome']
        api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            return None
        next_data = json.loads(el.string)
        api_json = next_data['props']['pageProps']
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    if api_json.get('siteHubSlug') and api_json['siteHubSlug'] == 'buyside':
        article_json = api_json['article']
        item = {}
        item['id'] = article_json['id']
        item['url'] = article_json['seo']['canonicalURL']
        item['title'] = article_json['title']
        dt = datetime.fromisoformat(article_json['publishedAt']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(article_json['updatedAt']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['authors'] = [{"name": x['fullName']} for x in article_json['authors']]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
        item['tags'] = []
        item['tags'].append(api_json['category'])
        item['tags'].append(article_json['subcategory']['name'])
        item['content_html'] = ''
        if article_json.get('heroSection'):
            if article_json['heroSection'].get('summary'):
                item['summary'] = article_json['heroSection']['summary']['label']
                item['content_html'] += '<p><em>' + article_json['heroSection']['summary']['label'] + '</em></p>'
            if article_json['heroSection'].get('featuredImage'):
                item['image'] = article_json['heroSection']['featuredImage']['url']
                item['content_html'] += utils.add_image(item['image'], article_json['heroSection']['featuredImage'].get('credit'))
        if 'summary' not in item and article_json['seo'].get('metaDescription'):
            item['summary'] = article_json['seo']['metaDescription']['url']
        if 'image' not in item and article_json['seo'].get('metaImage'):
            item['image'] = article_json['seo']['metaImage']['url']
        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item
        for block in article_json['blocks']:
            if block['__typename'] == 'strapiComponentSharedTextContent':
                item['content_html'] += block['content']
            elif block['__typename'] == 'strapiBuysideProductBlock':
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                if block['product'].get('image'):
                    item['content_html'] += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"></div>'.format(block['product']['image']['url'])
                item['content_html'] += '<div style="flex:1; min-width:256px;">'
                item['content_html'] += '<div style="font-weight:bold; text-transform:uppercase;">' + block['product']['brandName'] + '</div>'
                item['content_html'] += '<h3>' + block['product']['productHeadline'] + '</h3>'
                for it in block['product']['affiliateLinks']['customEcommerceLink']:
                    if it['price'] != it['originalPrice']:
                        text = '<span style="color:#ccc; font-size:0.8em; text-decoration:line-through;">${}</span> '.format(it['originalPrice'])
                    else:
                        text = ''
                    text = '${} at {}'.format(it['price'], it['merchant']['name'])
                    item['content_html'] += utils.add_button(it['url'], text)
                if block['product']['affiliateLinks']['amazonLink']:
                    if block['product']['affiliateLinks']['amazonLink']['price'] != block['product']['affiliateLinks']['amazonLink']['originalPrice']:
                        text = '<span style="color:#ccc; font-size:0.8em; text-decoration:line-through;">${}</span> '.format(block['product']['affiliateLinks']['amazonLink']['originalPrice'])
                    else:
                        text = ''
                    text += '${} at Amazon'.format(block['product']['affiliateLinks']['amazonLink']['price'])
                    item['content_html'] += utils.add_button(block['product']['affiliateLinks']['amazonLink']['url'], text)
                if block['product'].get('description'):
                    item['content_html'] += block['product']['description']
                item['content_html'] += '</div></div>'
            elif block['__typename'] == 'strapiComponentBlocksAuthorsBox':
                continue
            else:
                logger.warning('unhandled article block type ' + block['__typename'])
        return item

    # article_json = api_json['articleData']['attributes']
    article_json = api_json['articleData']

    item = {}
    item['id'] = article_json['originId']
    if article_json.get('canonicalUrl'):
        item['url'] = article_json['canonicalUrl']
    elif article_json.get('sourceUrl'):
        item['url'] = article_json['sourceUrl']
    elif api_json.get('articleUrl'):
        item['url'] = api_json['articleUrl']
    item['title'] = article_json['headline']['text']

    dt = datetime.fromisoformat(article_json['publishedDateTimeUtc'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedDateTimeUtc'])
    item['date_published'] = dt.isoformat()

    item['authors'] = []
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            if it['text'] not in authors:
                authors.append(it['text'])
        item['authors'] = [{"name": x} for x in authors]
    elif article_json.get('byline'):
        item['authors'] = []
        for it in article_json['byline']:
            for x in it['text'].split('|'):
                m = re.search(r'^(.*?)?by (.*?)?(for .*?)?$', x.strip(), flags=re.I)
                if m:
                    if m.group(1).strip():
                        item['authors'].append({"name": "{} ({})".format(m.group(2).strip(), m.group(1).strip())})
                    else:
                        item['authors'].append({"name": m.group(2).strip()})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif article_json.get('publisher'):
        item['author'] = {
            "name": article_json['publisher']
        }
        item['authors'].append(item['author'])

    item['tags'] = []
    item['tags'].append(article_json['sectionName'])
    item['tags'].append(article_json['sectionType'])
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if api_json.get('articleMeta') and api_json['articleMeta'].get('properties'):
        for it in api_json['articleMeta']['properties']:
            if it.get('type') and it['type'] == 'code':
                if it['codeType'] != 'author' and it['codeType'] != 'seo-path':
                    if it.get('properties') and it['properties'].get('name'):
                        if it['properties']['name'] not in item['tags']:
                            item['tags'].append(it['properties']['name'])
    if item.get('tags'):
        # Remove duplicates (case-insensitive)
        item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))
    else:
        del item['tags']

    article_links = api_json.get('articleLinks')

    if article_json.get('summary') and article_json['summary'].get('content'):
        item['summary'] = render_contents(article_json['summary']['content'], split_url.netloc, article_links)
    elif article_json.get('standFirst') and article_json['standFirst'].get('content'):
        item['summary'] = render_contents(article_json['standFirst']['content'], split_url.netloc, article_links)
    elif api_json.get('articleToolsProps') and api_json['articleToolsProps'].get('summary'):
        item['summary'] = api_json['articleToolsProps']['summary']
    elif api_json.get('snippet'):
        item['summary'] = render_contents(api_json['snippet'], split_url.netloc, article_links)
    if item.get('summary'):
        # Remove title
        item['summary'] = re.sub(r'<h2>{}</h2>'.format(item['title']), '', item['summary'], flags=re.I)

    item['content_html'] = ''
    if article_json.get('standfirst') and article_json['standfirst'].get('content'):
        item['content_html'] += '<p><em>{}</em></p>'.format(render_contents(article_json['standfirst']['content'], split_url.netloc, article_links))
    elif api_json.get('dek'):
        item['content_html'] += '<p><em>' + api_json['dek'] + '</em></p>'

    if article_json.get('leadInset'):
        lead_html = render_contents(article_json['leadInset'], split_url.netloc, article_links)
        if article_json['leadInset']['type'] == 'video':
            if article_json['leadInset'].get('video_service_props') and article_json['leadInset']['video_service_props'].get('jsonLD') and article_json['leadInset']['video_service_props']['jsonLD'].get('thumbnailUrl'):
                item['_image'] = article_json['leadInset']['video_service_props']['jsonLD']['thumbnailUrl']
        elif article_json['leadInset']['type'] == 'inset':
            if article_json['leadInset']['properties'].get('datatype') and article_json['leadInset']['properties']['datatype'] == 'Image':
                item['_image'] = article_json['leadInset']['properties']['urllarge']
            elif article_json['leadInset']['properties'].get('datatype') and article_json['leadInset']['properties']['datatype'] == 'AutoPlayVideoClip':
                item['_image'] = article_json['leadInset']['videoData']['thumbnail']
        if not item.get('_image'):
            m = re.search(r'src="([^"]+)"', lead_html)
            if m:
                item['_image'] = m.group(1)
    else:
        lead_html = ''

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('articleBody'):
        item['content_html'] += render_contents(article_json['articleBody'], split_url.netloc, article_links)
    elif article_json.get('body'):
        item['content_html'] += render_contents(article_json['body'], split_url.netloc, article_links)
    else:
        item['content_html'] += lead_html
        body_json = utils.get_url_json('https://www.mansionglobal.com/articles/{}?jsondata=y&noredirect=true&count=1'.format(item['id']), headers=headers)
        if body_json:
            body_soup = BeautifulSoup(body_json['body'], 'html.parser')
            if save_debug:
                utils.write_file(str(body_soup), './debug/body.html')

            el = body_soup.find('div', class_='paywall')
            if el:
                el.unwrap()

            # Remove comment sections
            for el in body_soup.find_all(text=lambda text: isinstance(text, Comment)):
                el.extract()

            for el in body_soup.find_all('a', href=re.compile(r'https://www\.mansionglobal\.com/quote/')):
                m = re.search(r'/quote/([^/]+)', el['href'])
                if m:
                    if 'wsj' in split_url.netloc:
                        # https://www.wsj.com/market-data/quotes/AAPL
                        el['href'] = el['href'].replace('https://www.mansionglobal.com/quote/', 'https://www.wsj.com/market-data/quotes/')
                    elif 'barrons' in split_url.netloc:
                        # https://www.wsj.com/market-data/quotes/AAPL
                        el['href'] = el['href'].replace('https://www.mansionglobal.com/quote/', 'https://www.barrons.com/market-data/stocks/')
                    elif 'marketwatch' in split_url.netloc:
                        # https://www.marketwatch.com/investing/stock/AAPL
                        el['href'] = el['href'].replace('https://www.mansionglobal.com/quote/', 'https://www.marketwatch.com/investing/stock/')
                    else:
                        logger.warning('unhandled stock quote link {} in {}'.format(el['href'], item['url']))
                    if el.get('class') and 'chiclet-wrapper' in el['class']:
                        stock_json = utils.get_url_json('https://api.foxbusiness.com/factset/stock-search?stockType=quoteInfo&identifiers=US:{}&isIndex=true'.format(m.group(1)))
                        if stock_json:
                            new_html = ' ({} ${:,.2f}'.format(stock_json['data'][0]['symbol'], stock_json['data'][0]['last'])
                            if stock_json['data'][0]['changePercent'] < 0:
                                el['style'] = 'color:red; text-decoration:none;'
                                new_html += ' ▼ '
                            else:
                                el['style'] = 'color:green; text-decoration:none;'
                                new_html += ' ▲ '
                            new_html += '{:,.2f}%)'.format(stock_json['data'][0]['changePercent'])
                            el.string = new_html
                            # new_el = BeautifulSoup(new_html, 'html.parser')
                            # el.insert(0, new_el)

            for el in body_soup.find_all(class_='media-object'):
                new_html = ''
                if 'type-InsetMediaIllustration' in el['class']:
                    it = el.find('img')
                    if it:
                        if it.get('srcset'):
                            img_src = utils.image_from_srcset(it['srcset'], 1200)
                        else:
                            img_src = it['src']
                        captions = []
                        it = el.find(class_='wsj-article-caption-content')
                        if it:
                            captions.append(it.decode_contents())
                        it = el.find(class_='wsj-article-credit')
                        if it:
                            captions.append(it.decode_contents())
                        new_html = utils.add_image(img_src, ' | '.join(captions))
                elif 'type-InsetMediaVideo' in el['class']:
                    it = el.find(class_='video-container')
                    if it:
                        video_item = get_content('https://www.wsj.com/video/' + it['data-src'], {"embed": True}, {}, False)
                        if video_item:
                            new_html = video_item['content_html']
                elif 'type-InsetTweet' in el['class']:
                    it = el.select('blockquote.twitter-tweet > a')
                    if it:
                        new_html = utils.add_embed(it[0]['href'])
                elif 'type-InsetDynamic' in el['class']:
                    group_captions = []
                    it = el.find(class_='origami-grouped-caption')
                    if it:
                        group_captions.append(it.decode_contents())
                    it = el.find(class_='origami-grouped-credit')
                    if it:
                        group_captions.append(it.decode_contents())
                    new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                    for it in el.find_all(class_='origami-item'):
                        if it.figure and it.figure.img:
                            captions = []
                            if not group_captions:
                                cap = it.find(class_='origami-caption')
                                if cap:
                                    captions.append(cap.decode_contents())
                                cap = it.find(class_='origami-credit')
                                if cap:
                                    captions.append(cap.decode_contents())
                            new_html += '<div style="flex:1; min-width:256px; margin:auto;">' + utils.add_image(it.figure.img['src'], ' | '.join(captions), link=it.figure.img['src']) + '</div>'
                    new_html += '</div>'
                    if group_captions:
                        new_html += '<div><small>' + ' | '.join(group_captions) + '</div>'
                elif 'type-InsetArticleReader' in el['class']:
                    it = el.find(class_='audioplayer')
                    if it:
                        video_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=read-to-me&query={}&fields=adZone,audioURL,audioURLPanoply,author,body,column,description,doctypeID,duration,episodeNumber,formattedCreationDate,guid,keywords,linkURL,name,omniPublishDate,omniVideoFormat,playbackSite,podcastName,podcastSubscribeLinks,podcastUrl,rootId,thumbnailImageManager,thumbnailList,titletag,type,wsj-section,wsj-subsection'.format(it['data-sbid'])
                        video_json = utils.get_url_json(video_url)
                        if video_json:
                            duration = utils.calc_duration(int(video_json['items'][0]['duration']))
                            new_html = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to article</a> ({2})</span></div><div>&nbsp;</div>'.format(video_json['items'][0]['audioURL'], config.server, duration)
                elif 'type-InsetPageRule' in el['class']:
                    new_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
                elif 'type-InsetPullQuote' in el['class']:
                    for it in el.find_all(class_=['l-qt', 'r-qt']):
                        it.decompose()
                    it = el.find('p', class_='pullquote-content')
                    if it:
                        new_html += utils.add_pullquote(it.decode_contents())
                elif 'type-InsetRichText' in el['class']:
                    it = el.find('h4')
                    if it and re.search(r'MORE IN|SHARE YOUR THOUGHTS', it.get_text().strip()):
                        el.decompose()
                        continue
                elif 'type-InsetBigTopHero' in el['class'] or 'type-InsetNewsletterSignup' in el['class']:
                    # Skip
                    el.decompose()
                    continue
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled media-object class {} in {}'.format(el['class'], item['url']))

            item['content_html'] += body_soup.find(class_='article-wrap').decode_contents()
        elif api_json.get('body'):
            item['content_html'] += render_contents(api_json['body'], split_url.netloc, article_links)
            if api_json.get('encryptedDocumentKey'):
                logger.debug('decrypting document...')
                content = decrypt_content(item['url'], api_json['encryptedDocumentKey'], api_json['encryptedDataHash'])
                if content:
                    logger.debug('...success')
                    content_json = json.loads(content)
                    if save_debug:
                        utils.write_file(content_json, './debug/content.json')
                    item['content_html'] += render_contents(content_json, split_url.netloc, article_links)
                else:
                    logger.warning('...failed to decrypt document')

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.wsj.com/news/rss-news-and-feeds
    if url.endswith('.xml'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    feed = {}
    articles = []
    feed_title = ''
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'window\.__STATE__'))
    if el:
        i = el.string.find('{')
        j = el.string.rfind('}')
        state_json = json.loads(el.string[i:j+1])
        if save_debug:
            utils.write_file(state_json, './debug/feed.json')
        for key, val in state_json['data'].items():
            if key.startswith('article'):
                articles.append(val['data']['data']['url'])
        if 'topics' in url:
            feed_title = state_json['context']['sectionTitle']
        elif 'author' in url:
            if state_json['context'].get('authorData'):
                feed_title = state_json['context']['authorData']['name']['fullname']
            elif state_json['context'].get('data'):
                feed_title = state_json['context']['data']['name']['fullname']
        if feed_title:
            if state_json['context'].get('application'):
                feed_title += ' | ' + state_json['context']['application']
            else:
                feed_title += ' | ' + split_url.netloc
    else:
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if save_debug:
                utils.write_file(next_data, './debug/feed.json')
            if 'stock-picks' in paths:
                feed_title = '{} | {}'.format(next_data['props']['pageProps']['analytics']['page_subsection'], next_data['props']['pageProps']['analytics']['page_site'])
                for block in next_data['props']['pageProps']['stockPicksContent']['blocks']:
                    if block['$type'] == 'News.MoreHeadlinesCard':
                        for blk in block['blocks']:
                            if blk['$type'] == 'News.StoryCard':
                                articles.append(blk['url'])
            else:
                if next_data['props']['pageProps'].get('latestArticles'):
                    for article in next_data['props']['pageProps']['latestArticles']:
                        if article.get('articleUrl'):
                            articles.append(article['articleUrl'])
                if next_data['props']['pageProps'].get('latestVideos'):
                    for article in next_data['props']['pageProps']['latestVideos']:
                        if article.get('articleUrl'):
                            articles.append(article['articleUrl'])

    if False:
        gql_url = 'https://shared-data.dowjones.io/gateway/graphql'
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "apollographql-client-name": "wsj:autofeed",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "pragma": "no-cache",
            "sec-ch-ua": "\"Chromium\";v=\"118\", \"Microsoft Edge\";v=\"118\", \"Not=A?Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.46"
        }
        gql_data = {
            "query": "\nquery ArticlesByContentType($searchQuery: SearchQuery!, $contentType: [SearchContentType], $page: Int) {\n  articlesByContentType(searchQuery: $searchQuery, contentType: $contentType, page: $page) {\n    headline {\n      text\n    }\n    columnName\n    publishedDateTimeUtc\n    seoId\n    seoPath {\n      value\n    }\n    sourceUrl\n    type\n    liveDateTimeUtc\n    meta {\n      metrics {\n        timeToReadMinutes\n      }\n    }\n    byline\n    flattenedSummary {\n      headline {\n        text\n      }\n      image {\n        properties {\n          location\n        }\n        src {\n          imageId\n          baseUrl\n        }\n        id\n        altText\n        altImages {\n          url\n          width\n          height\n        }\n        width\n      }\n      description {\n        content {\n          text\n        }\n      }\n      list {\n        items {\n          text\n          context {\n            ... on LinkArticleContext {\n              id\n              uri\n            }\n          }\n        }\n      }\n    }\n    articleFlashline {\n      text\n    }\n    authors {\n      id\n      text\n      content {\n        id,\n        hedcutImage,\n        byline,\n        seoName,\n        title,\n        url\n      }\n    }\n    typeDisplayName\n  }\n}\n",
            "variables": {
                "contentType": ["ARTICLE"],
                "page": 1,
                "searchQuery": {
                    "and": [
                        {
                            "terms": {
                                "key": "Product",
                                "value": [
                                    "WSJ.com", "WSJ Blogs"
                                ]
                            }
                        }
                    ],
                    "not": [
                        {
                            "terms": {
                                "key": "SectionName",
                                "value": [
                                    "Opinion"
                                ]
                            }
                        },
                        {
                            "terms": {
                                "key": "SectionName",
                                "value": [
                                    "Breaking News China Traditional",
                                    "Corrections and Amplifications",
                                    "Decos and Corrections",
                                    "Direct Push Alert",
                                    "DJON Wire",
                                    "NewsPlus",
                                    "Opinion",
                                    "WSJ Puzzles"
                                ]
                            }
                        },
                        {
                            "terms": {
                                "key": "SectionType",
                                "value": [
                                    "Breaking News China Simplified",
                                    "Board Pack Exclusive",
                                    "Cryptic",
                                    "Crossword",
                                    "Crossword Contest",
                                    "Deco Summary (Content)",
                                    "Deco Summary (Plain)",
                                    "Deco Summary Barrons Cover Story",
                                    "Deco Summary Barrons Market Week",
                                    "Deco Summary Barrons Preview",
                                    "Deco Summary Japanese", "Deco Summary Liondoor",
                                    "Infogrfx Slide Show",
                                    "Infogrfx House Of The Day",
                                    "Pepper%20%26%20Salt",
                                    "Pro Bankruptcy Data Tables", "Recipes",
                                    "Style & Substance", "Whats News",
                                    "Whats News Business Finance",
                                    "Whats News World Wide"
                                ]
                            }
                        }
                    ],
                    "or": [
                        {
                            "terms": {
                                "key": "PrimaryDJEThing",
                                "value": [
                                    "tech/personal-tech"
                                ]
                            }
                        },
                        {
                            "terms": {
                                "key": "SecondaryDJEThing",
                                "value": [
                                    "tech/personal-tech"
                                ]
                            }
                        }
                    ],
                    "sort": [
                        {
                            "key": "LiveDate",
                            "order": "desc"
                        }
                    ]
                }
            }
        }

    if articles:
        n = 0
        feed_items = []
        for article in articles:
            if save_debug:
                logger.debug('getting content for ' + article)
            item = get_content(article, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
        feed = utils.init_jsonfeed(args)
        if feed_title:
            feed['title'] = feed_title
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
