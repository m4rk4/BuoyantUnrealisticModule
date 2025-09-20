import base64, basencode, json, math, random, re
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def make_article(article_json):
    # https://x.com/X/status/1814437564989702557
    article_html = ''
    if article_json.get('cover_media'):
        article_html += '<div><img src="{}?format=jpg&name=small" style="width:100%; border-radius:10px;"></div>'.format(article_json['cover_media']['media_info']['original_img_url'])
    if article_json.get('title'):
        article_html += '<div style="font-size:1.2em; font-weight:bold;">' + article_json['title'] + '</div>'
    for block in article_json['content_state']['blocks']:
        if block['type'] == 'atomic':
            for entity in block['entityRanges']:
                entity_value = next((it['value'] for it in article_json['content_state']['entityMap'] if int(it['key']) == entity['key']), None)
                if entity_value['type'] == 'TWEET':
                    tweet_item = get_content('https://twitter.com/__/status/' + entity_value['data']['tweetId'], {}, {}, False)
                    if tweet_item:
                        article_html += tweet_item['content_html']
                elif entity_value['type'] == 'MEDIA':
                    for media in entity_value['data']['mediaItems']:
                        media_info = next((it['media_info'] for it in article_json['media_entities'] if it['media_id'] == media['mediaId']), None)
                        if media_info['__typename'] == 'ApiImage':
                            article_html += '<div><a href="{0}" target="_blank"><img src="{0}?format=jpg&name=small" style="width:100%; border-radius:10px;"></a></div>'.format(media_info['original_img_url'])
                        elif media_info['__typename'] == 'ApiVideo':
                            video = next((it for it in media_info['variants'] if it['content_type'].lower() == 'application/x-mpegurl'), None)
                            if not video:
                                videos = [it for it in media_info['variants'] if it['content_type'].lower() == 'video/mp4']
                                video = utils.closest_dict(videos, 'bit_rate', 1000000)
                            if video['content_type'] == 'video/mp4':
                                video_src = video['url']
                            else:
                                video_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(video['url']), quote_plus(video['content_type']), quote_plus(media_info['preview_image']['original_img_url']))
                            thumb = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(media_info['preview_image']['original_img_url'] + '?format=jpg&name=small'))
                            article_html += '<div><a href="{}" target="_blank"><img src="{}" style="width:100%; border-radius:10px;"></a></div>'.format(video_src, thumb)
                elif entity_value['type'] == 'DIVIDER':
                        article_html += '<hr/>'
                else:
                    logger.warning('unhandled atomic entity value type ' + entity_value['type'])
        else:
            if len(block['entityRanges']) > 0 or len(block['inlineStyleRanges']) > 0:
                entities = block['entityRanges'].copy() + block['inlineStyleRanges'].copy()
                indices = []
                for entity in entities:
                    if 'style' in entity:
                        if entity['style'] == 'Bold':
                            entity['start_tag'] = '<b>'
                            entity['end_tag'] = '</b>'
                        elif entity['style'] == 'Italic':
                            entity['start_tag'] = '<i>'
                            entity['end_tag'] = '</i>'
                        elif entity['style'] == 'Strikethrough':
                            entity['start_tag'] = '<s>'
                            entity['end_tag'] = '</s>'
                        else:
                            logger.warning('unhandled entity style ' + entity['style'])
                    elif 'key' in entity:
                        entity_value = next((it['value'] for it in article_json['content_state']['entityMap'] if int(it['key']) == entity['key']), None)
                        if entity_value['type'] == 'LINK':
                            entity['start_tag'] = '<a href="{}">'.format(entity_value['data']['url'])
                            entity['end_tag'] = '</a>'
                        elif entity_value['type'] == 'TWEMOJI':
                            # use the default unicode emoji
                            entity['from_index'] = -1
                            entity['to_index'] = -1
                            continue
                        else:
                            logger.warning('unhandled entity value type ' + entity_value['type'])
                    entity['from_index'] = entity['offset']
                    entity['to_index'] = entity['offset'] + entity['length']
                    indices.append(entity['from_index'])
                    indices.append(entity['to_index'])
                # remove duplicates and sort
                indices = sorted(list(set(indices)))
                n = 0
                text = ''
                for i in indices:
                    text += block['text'][n:i]
                    from_entities = list(filter(lambda entities: entities['from_index'] == i and entities.get('start_tag'), entities))
                    from_entities = sorted(from_entities, key=lambda x: x['to_index'])
                    for j, entity in enumerate(from_entities):
                        text += entity['start_tag']
                        entity['order'] = i + j
                    to_entities = list(filter(lambda entities: entities['to_index'] == i and entities.get('end_tag'), entities))
                    to_entities = sorted(to_entities, key=lambda x: (x['from_index'], x['order']), reverse=True)
                    for entity in to_entities:
                        text += entity['end_tag']
                    n = i
                text += block['text'][n:]
            else:
                text = block['text']

            if block['type'] == 'unstyled':
                article_html += '<p>' + text + '</p>'
            elif block['type'] == 'header-one':
                article_html += '<div style="font-size:1.2em; font-weight:bold;">' + text + '</div>'
            elif block['type'] == 'header-two':
                article_html += '<div style="font-size:1.1em; font-weight:bold;">' + text + '</div>'
            elif block['type'] == 'blockquote':
                article_html += utils.add_blockquote(text, False)
            else:
                logger.warning('unhandled article block type ' + block['type'])
    return article_html


def replace_tombstone_entities(block):
    if not block.get('entities'):
        return block['text']
    entities = block['entities'].copy()
    indices = []
    for entity in entities:
        indices.append(entity['from_index'])
        indices.append(entity['to_index'])
        if entity.get('ref'):
            if '/t.co/' in entity['ref']['url']:
                link = utils.get_redirect_url(entity['ref']['url']['url'])
            else:
                link = entity['ref']['url']
            entity['start_tag'] = '<a href="{}">'.format(link)
            entity['end_tag'] = '</a>'
    # remove duplicates and sort
    indices = sorted(list(set(indices)))
    n = 0
    text = ''
    for i in indices:
        text += block['text'][n:i]
        from_entities = list(filter(lambda entities: entities['from_index'] == i and entities.get('start_tag'), entities))
        from_entities = sorted(from_entities, key=lambda x: x['to_index'])
        for j, entity in enumerate(from_entities):
            text += entity['start_tag']
            entity['order'] = i + j
        to_entities = list(filter(lambda entities: entities['to_index'] == i and entities.get('end_tag'), entities))
        to_entities = sorted(to_entities, key=lambda x: (x['from_index'], x['order']), reverse=True)
        for entity in to_entities:
            text += entity['end_tag']
        n = i
    text += block['text'][n:]
    return text


def replace_birdwatch_entities(block):
    if not block.get('entities'):
        return block['text']
    entities = block['entities'].copy()
    indices = []
    for entity in entities:
        indices.append(entity['fromIndex'])
        indices.append(entity['toIndex'])
        if entity.get('ref'):
            if '/t.co/' in entity['ref']['url']['url']:
                link = utils.get_redirect_url(entity['ref']['url']['url'])
            else:
                link = entity['ref']['url']['url']
            entity['start_tag'] = '<a href="{}">'.format(link)
            entity['end_tag'] = '</a>'
    # remove duplicates and sort
    indices = sorted(list(set(indices)))
    n = 0
    text = ''
    for i in indices:
        text += block['text'][n:i]
        from_entities = list(filter(lambda entities: entities['fromIndex'] == i and entities.get('start_tag'), entities))
        from_entities = sorted(from_entities, key=lambda x: x['toIndex'])
        for j, entity in enumerate(from_entities):
            text += entity['start_tag']
            entity['order'] = i + j
        to_entities = list(filter(lambda entities: entities['toIndex'] == i and entities.get('end_tag'), entities))
        to_entities = sorted(to_entities, key=lambda x: (x['fromIndex'], x['order']), reverse=True)
        for entity in to_entities:
            text += entity['end_tag']
        n = i
    text += block['text'][n:]
    return text


def get_expanded_url(tweet_json, link):
    for url in tweet_json['entities']['urls']:
        if url['url'] == link:
            return url['expanded_url']
    return link


def make_card(card_json, tweet_json):
    # Card types: https://developer.twitter.com/en/docs/twitter-for-websites/cards/overview/abouts-cards
    binding_values = card_json['binding_values']
    card_type = 0
    card_html = ''
    card_link = ''
    link_text = ''
    img = ''
    img_link = ''
    card_desc = ''

    if card_json['name'] == 'summary' or card_json['name'] == 'direct_store_link_app':
        card_type = 1
        card_link = get_expanded_url(tweet_json, card_json['url'])
        title = binding_values['title']['string_value']
        if binding_values.get('description') and binding_values['description'].get('string_value'):
            card_desc = binding_values['description']['string_value']
        img_src = ''
        img_keys = ['summary_photo_image_small', 'thumbnail_image_large', 'thumbnail']
        for key in img_keys:
            if binding_values.get(key):
                img_src = '{}/image?url={}&crop=0&width=128'.format(config.server, quote_plus(binding_values[key]['image_value']['url']))
        if not img_src:
            img_src = '{}/image?width=128&height=128'.format(config.server, quote_plus(img_src))
        img = '<img src={} style="border-top-left-radius:10px; border-bottom-left-radius:10px;" />'.format(img_src)

    elif card_json['name'] == 'player':
        card_type = 1
        card_link = binding_values['player_url']['string_value']
        if 'youtube' in card_link:
            m = re.match(r'https:\/\/www\.youtube\.com\/embed\/([^#\&\?]{11})', card_link)
            card_link = 'https://www.youtube.com/watch?v=' + m.group(1)
            img_link = '{}/video?url={}'.format(config.server, quote_plus(card_link))
        title = binding_values['title']['string_value']
        if binding_values.get('description'):
            card_desc = binding_values['description']['string_value']
        img_src = '{}/image?url={}&crop=0&width=128&overlay=video'.format(config.server, quote_plus(binding_values['player_image_large']['image_value']['url']))
        img = '<img src={} style="border-top-left-radius:10px; border-bottom-left-radius:10px;" />'.format(img_src)

    elif card_json['name'] == 'summary_large_image':
        card_type = 2
        card_link = get_expanded_url(tweet_json, card_json['url'])
        title = binding_values['title']['string_value']
        if binding_values.get('description') and binding_values['description'].get('string_value'):
            card_desc = binding_values['description']['string_value']
        img_src = ''
        img_keys = ['summary_photo_image_original', 'summary_photo_image', 'photo_image_full_size', 'thumbnail_image_large']
        for key in img_keys:
            if binding_values.get(key):
                img_src = '{}/image?url={}&width=522'.format(config.server, quote_plus(binding_values[key]['image_value']['url']))
        if img_src:
            img = '<img src={} style="border-top-left-radius:10px; border-top-right-radius:10px;" />'.format(img_src)
        else:
            card_type = 1
            img_src = '{}/image?width=128&height=128'.format(config.server, quote_plus(img_src))
            img = '<img src={} style="border-top-left-radius:10px; border-bottom-left-radius:10px;" />'.format(img_src)

    elif card_json['name'] == 'unified_card':
        # https://twitter.com/WEURO/status/1653368030037004288
        unified_card = json.loads(binding_values['unified_card']['string_value'])
        utils.write_file(unified_card, './debug/card.json')
        if unified_card['type'] == 'image_carousel_website':
            images = []
            for component in unified_card['components']:
                object = unified_card['component_objects'][component]
                if object['type'] == 'swipeable_media':
                    images = []
                    for it in object['data']['media_list']:
                        media = unified_card['media_entities'][it['id']]
                        if media['type'] == 'photo':
                            image = {}
                            image['src'] = media['media_url_https']
                            if it.get('destination'):
                                destination = unified_card['destination_objects'][it['destination']]
                                image['link'] = destination['data']['url_data']['url']
                            else:
                                image['link'] = ''
                            images.append(image)
                        else:
                            logger.warning('unhandled unified card media type ' + media['type'])
                elif object['type'] == 'details':
                    if object['data'].get('title'):
                        title = object['data']['title']['content']
                    if object['data'].get('subtitle'):
                        link_text = object['data']['subtitle']['content']
                    if object['data'].get('destination'):
                        destination = unified_card['destination_objects'][object['data']['destination']]
                        card_link = destination['data']['url_data']['url']
            card_html = '<figure style="width:100%; margin:0; padding:0; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
            for image in images[:-1]:
                if image.get('link'):
                    card_html += '<a href="{}"><img src={} style="width:100%; border-radius:10px;" /></a><div>&nbsp;</div>'.format(image['link'], image['src'])
                else:
                    card_html += '<img src={} style="width:100%; border-radius:10px;" /><div>&nbsp;</div>'.format(image['src'])
            image = images[-1]
            if image.get('link'):
                card_html += '<a href="{}"><img src={} style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(image['link'], image['src'])
            else:
                card_html += '<img src={} style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" />'.format(image['src'])
            card_html += '<div style="margin:8px;"><small>{}</small><br/><a href="{}"><b>{}</b></a>'.format(link_text, card_link, title)
            if card_desc:
                card_html += '<br/>' + card_desc
            card_html += '</div></figure>'
        elif unified_card['type'] == 'image_website' or unified_card['type'] == 'video_website':
            images = []
            videos = []
            destinations = []
            for component in unified_card['components']:
                object = unified_card['component_objects'][component]
                if object['type'] == 'media':
                    media = unified_card['media_entities'][object['data']['id']]
                    if media['type'] == 'photo':
                        images.append(media['media_url_https'])
                    elif media['type'] == 'video':
                        poster = '{}/image?url={}&width=500&overlay=video'.format(config.server, media['media_url_https'])
                        video = next((it for it in media['video_info']['variants'] if it['content_type'] == 'application/x-mpegurl'), None)
                        if video:
                            videos.append({
                                "src": "{}/videojs?src={}&type={}&poster={}".format(config.server, quote_plus(video['url']), quote_plus(video['content_type']), quote_plus(poster)),
                                "poster": poster
                            })
                        else:
                            video = utils.closest_dict([it for it in media['video_info']['variants'] if it['content_type'] == 'video/mp4'], 'bitrate', 1000000)
                            if video:
                                videos.append({"src": video['url'], "poster": poster})
                            else:
                                logger.warning('unhandled unified video card')
                    else:
                        logger.warning('unhandled unified card media type ' + media['type'])
                elif object['type'] == 'details':
                    if object['data'].get('title'):
                        title = object['data']['title']['content']
                    if object['data'].get('subtitle'):
                        link_text = object['data']['subtitle']['content']
                    if object['data'].get('destination'):
                        destination = unified_card['destination_objects'][object['data']['destination']]
                        destinations.append(destination['data']['url_data'])
                        card_link = destination['data']['url_data']['url']
            for i, image in enumerate(images):
                card_html = '<figure style="width:100%; margin:0; padding:0; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                card_html += '<a href="{}"><img src={} style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(destinations[i]['url'], image)
                card_html += '<div style="margin:8px;"><small><a href="{}">{}</a></small></div>'.format(destinations[i]['url'], destinations[i]['vanity'])
                if title:
                    card_html += '<div style="margin:8px; font-weight:bold;"><a href="{}">{}</a></div>'.format(destinations[i]['url'], title)
                card_html += '</figure>'
            for i, video in enumerate(videos):
                card_html = '<figure style="width:100%; margin:0; padding:0; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                card_html += '<a href="{}"><img src={} style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(video['src'], video['poster'])
                card_html += '<div style="margin:8px;"><small><a href="{}">{}</a></small></div>'.format(destinations[i]['url'], destinations[i]['vanity'])
                if title:
                    card_html += '<div style="margin:8px; font-weight:bold;"><a href="{}">{}</a></div>'.format(destinations[i]['url'], title)
                card_html += '</figure>'
        else:
            logger.warning('unhandled unified card type ' + unified_card['type'])

    elif 'event' in card_json['name']:
        card_type = 2
        card_link = get_expanded_url(tweet_json, card_json['url'])
        title = binding_values['event_title']['string_value']
        card_desc = binding_values['event_subtitle']['string_value']
        img_src = binding_values['event_thumbnail']['image_value']['url']

    elif re.search(r'poll\dchoice_text_only', card_json['name']):
        # https://twitter.com/elonmusk/status/1604617643973124097
        # https://twitter.com/TheMuse/status/783364112168415232
        card_type = 3
        n = 1
        total_count = 0
        max_count = 0
        n_max = 0
        while 'choice{}_label'.format(n) in binding_values:
            count = int(binding_values['choice{}_count'.format(n)]['string_value'])
            total_count += count
            if count > max_count:
                max_count = count
                n_max = n
            n = n + 1
        card_html = '<div style="width:100%;">'
        for i in range(1, n):
            count = int(binding_values['choice{}_count'.format(i)]['string_value'])
            label = binding_values['choice{}_label'.format(i)]['string_value']
            if i == n_max:
                style = ' style="font-weight:bold;"'
                color = 'lightblue'
            else:
                style = ''
                color = 'lightgrey'
            pct = float(count / total_count * 100)
            if pct >= 50:
                card_html += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, {} {:.0f}%, white {:.0f}%);"><p{}>{}</p><p{}>{:.1f}%</p></div>'.format(color, pct, 100 - pct, style, label, style, pct)
            else:
                card_html += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {:.0f}%, {} {:.0f}%);"><p{}>{}</p><p{}>{:.1f}%</p></div>'.format(100 - pct, color, pct, style, label, style, pct)
        card_html += '</div><div><small>'
        if binding_values['counts_are_final']['boolean_value'] == True:
            card_html += 'Final results'
        else:
            card_html += 'Polling in progress'
        card_html += '&nbsp;&bull;&nbsp;{} votes'.format(total_count)
        dt = datetime.fromisoformat(
            binding_values['last_updated_datetime_utc']['string_value'].replace('Z', '+00:00'))
        card_html += '&nbsp;&bull;&nbsp;Last updated {}</small></div>'.format(utils.format_display_date(dt, date_only=True))

    elif card_json['name'] == 'promo_website':
        card_type = 2
        card_link = binding_values['website_dest_url']['string_value']
        title = binding_values['title']['string_value']
        img_src = binding_values['promo_image']['image_value']['url']

    elif 'promo_video_website' in card_json['name']:
        # Only shows the image not the promo video
        card_type = 2
        card_link = binding_values['website_dest_url']['string_value']
        title = binding_values['title']['string_value']
        img_src = binding_values['player_image']['image_value']['url']

    elif ':broadcast' in card_json['name']:
        # TODO: handle broadcast video src: https://twitter.com/i/broadcasts/1mnGeAXPyWNGX
        api_json = utils.get_url_json('https://api.x.com/1.1/broadcasts/show.json?ids=' + binding_values['broadcast_id']['string_value'])
        if api_json:
            card_type = 2
            broadcast = api_json['broadcasts'][binding_values['broadcast_id']['string_value']]
            live_stream = utils.get_url_json('https://api.x.com/1.1/live_video_stream/status/{}.json?client=web&use_syndication_guest_id=false&cookie_set_host=x.com'.format(broadcast['media_key']))
            if live_stream:
                # TODO: CORS proxy???
                video_src = config.server + '/proxy/' + live_stream['source']['noRedirectPlaybackUrl']
                card_link = '{}/videojs?src={}&type=application%2Fx-mpegURL&poster={}'.format(config.server, quote_plus(video_src), quote_plus(binding_values['broadcast_thumbnail']['image_value']['url']))
            else:
                card_link = binding_values['broadcast_url']['string_value']
            link_text = '<div style="font-size:0.9em;"><a href="https://x.com/{}" style="text-decoration:none;"><img style="float:left; width:1em; height:1em; border-radius:50%;" src="{}" />&nbsp;<b>{}</b>&nbsp;@{}</a></div>'.format(broadcast['twitter_username'], broadcast['profile_image_url'], broadcast['user_display_name'], broadcast['twitter_username'])
            title = broadcast['status']
            #img_src = broadcast['image_url']
            img_src = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(binding_values['broadcast_thumbnail']['image_value']['url']))
        else:
            card_type = 2
            card_link = binding_values['broadcast_url']['string_value']
            title = binding_values['broadcast_title']['string_value']
            img_src = binding_values['broadcast_thumbnail']['image_value']['url']
    else:
        logger.warning('unknown twitter card name ' + card_json['name'])
        return ''

    if not link_text:
        if binding_values.get('vanity_url'):
            link_text = binding_values['vanity_url']['string_value']
        elif card_link:
            link_text = urlsplit(card_link).netloc
        else:
            link_text = ''
    if not img_link:
        img_link = card_link

    if card_type == 1:
        card_html += '<table style="width:100%; margin:0; padding:0; border:1px solid light-dark(#333,#ccc); border-radius:10px; border-spacing:0;"><tr>'
        card_html += '<td style="line-height:0; width:128px; height:128px; padding:0 8px 0 0; border-collapse:collapse;"><a href="{}">{}</a></td>'.format(img_link, img)
        card_html += '<td style="padding:0; border-collapse:collapse; vertical-align:top;"><div style="max-height:128px; overflow:hidden;"><small>{}</small><br/><a href="{}"><b>{}</b></a><br/>{}</div></td>'.format(link_text, card_link, title, card_desc)
        card_html += '</tr></table>'
    elif card_type == 2:
        desc = '<div style="margin:8px;">'
        if link_text.startswith('<div'):
            desc += link_text
        else:
            desc += '<small>' + link_text + '</small><br/>'
        desc += '<a href="{}"><b>{}</b></a>'.format(card_link, title)
        if card_desc:
            desc += '<br/>' + card_desc
        desc += '</div>'
        card_html += utils.add_image(img_src, '', link=card_link, img_style="border-top-left-radius:10px; border-top-right-radius:10px;", fig_style="margin:0; padding:0; border:1px solid light-dark(#333,#ccc); border-radius:10px;", desc=desc)
    return card_html


def make_tweet(tweet_json, ref_tweet_url, is_parent=False, is_quoted=False, is_reply=0, has_parent=False):
    media_html = ''
    quoted_html = ''
    entities = tweet_json['entities']
    text_html = tweet_json['text'].strip()
    i = tweet_json['display_text_range'][0]
    j = tweet_json['display_text_range'][1]
    # if j > 0 and i < j and (text_html[i:j][-1] == '…' or (text_html[i:j][-1] == ' ' and text_html[i:j][-2] == '…')):
    if 'note_tweet' in tweet_json and tweet_json['note_tweet'].get('id'):
        logger.warning('truncated text - getting tweet detail from api')
        tweet_detail = get_tweet_result_by_api('https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_json['id_str']))
        if tweet_detail:
            try:
                if tweet_detail['data']['tweetResult']['result'].get('note_tweet'):
                    text_html = tweet_detail['data']['tweetResult']['result']['note_tweet']['note_tweet_results']['result']['text']
                    entities = tweet_detail['data']['tweetResult']['result']['note_tweet']['note_tweet_results']['result']['entity_set']
                elif tweet_detail['data']['tweetResult']['result'].get('tweet') and tweet_detail['data']['tweetResult']['result']['tweet'].get('note_tweet'):
                    text_html = tweet_detail['data']['tweetResult']['result']['tweet']['note_tweet']['note_tweet_results']['result']['text']
                    entities = tweet_detail['data']['tweetResult']['result']['tweet']['note_tweet']['note_tweet_results']['result']['entity_set']
                else:
                    logger.warning('unhandled tweetResult')
            except:
                logger.warning('failed to get full text')
                pass
        else:
            logger.warning('failed to get full text')

    def replace_entity(matchobj):
        if matchobj.group(1) == '@':
            return '<a href="https://twitter.com/{0}">@{0}</a>'.format(matchobj.group(2))
        elif matchobj.group(1) == '#':
            return '<a href="https://twitter.com/hashtag/{0}">#{0}</a>'.format(matchobj.group(2))
        elif matchobj.group(1) == '$':
            # don't match dollar amounts
            if not matchobj.group(2).isnumeric():
                return '<a href="https://twitter.com/search?q=%24{0}&src=cashtag_click">${0}</a>'.format(
                    matchobj.group(2))
        return matchobj.group(0)

    text_html = re.sub(r'(@|#|\$)(\w+)', replace_entity, text_html, flags=re.I)

    if entities.get('media'):
        for media in entities['media']:
            text_html = text_html.replace(media['url'], '')

    if entities.get('urls'):
        for url in entities['urls']:
            if text_html.strip().endswith(url['url']):
                if not 'twitter.com' in url['expanded_url']:
                    if tweet_json.get('card') and (url['url'] == tweet_json['card']['url']):
                        # If it's a card, remove the link, we'll add the card later
                        text_html = text_html.replace(url['url'], '')
                    else:
                        # If not a card, format the link
                        text_html = text_html.replace(url['url'], '<a href="{}">{}</a>'.format(url['expanded_url'], url['display_url']))
                else:
                    # Twitter links are often quoted tweets
                    if tweet_json.get('quoted_tweet') and (tweet_json['quoted_tweet']['id_str'] in url['expanded_url']):
                        text_html = text_html.replace(url['url'], '')
                    else:
                        # If not a quoted tweet, format the link
                        text_html = text_html.replace(url['url'], '<a href="{}">{}</a>'.format(url['expanded_url'], url['display_url']))
            else:
                text_html = text_html.replace(url['url'], '<a href="{}">{}</a>'.format(url['expanded_url'], url['display_url']))

    if tweet_json.get('mediaDetails'):
        gallery_images = []
        gallery_html = ''
        n = len(tweet_json['mediaDetails'])
        if n > 1:
            gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for media in tweet_json['mediaDetails']:
            if media['type'] == 'video':
                video_hls = next((it for it in media['video_info']['variants'] if it['content_type'].lower() == 'application/x-mpegurl'), None)
                video_mp4 = utils.closest_dict(media['video_info']['variants'], 'bitrate', 1000000)
                if video_hls or video_mp4:
                    if video_hls:
                        video_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(video_hls['url']), quote_plus(video_hls['content_type']), quote_plus(media['media_url_https']))
                    else:
                        video_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(video_mp4['url']), quote_plus(video_mp4['content_type']), quote_plus(media['media_url_https']))
                    thumb = config.server + '/image?url=' + quote_plus(media['media_url_https'] + '?format=jpg&name=small')
                    if media['original_info']['height'] > media['original_info']['width']:
                        thumb += '&letterbox=%28640%2C640%29&color=%23444'
                    thumb += '&overlay=video'
                    if tweet_json['user']['screen_name'].lower() not in media['expanded_url'].lower():
                        media_user = list(filter(None, urlsplit(media['expanded_url']).path[1:].split('/')))[0]
                        caption = '<div><small>From <a href="{}">@{}</a></small></div>'.format(media['expanded_url'], media_user)
                    else:
                        caption = ''
                    if n == 1:
                        media_html += '<div><a href="{}" target="_blank"><img style="width:100%; border-radius:10px;" src="{}" /></a></div>{}'.format(video_src, thumb, caption)
                    else:
                        gallery_html += '<div style="flex:1; min-width:200px;"><a href="{}" target="_blank"><img src="{}" style="display:block; width:100%; border-radius:10px;" /></a></div>{}'.format(video_src, thumb, caption)
                        if video_mp4:
                            gallery_images.append({"src": video_mp4['url'], "caption": "", "thumb": thumb})
                        else:
                            caption = '<a href={}" target="_blank">Click to play video</a>'.format(video_src)
                            gallery_images.append({"src": media['media_url_https'], "caption": caption, "thumb": thumb})
            elif media['type'] == 'photo':
                img_src = media['media_url_https']
                thumb = img_src + '?format=jpg&name=small'
                if media['original_info']['height'] > media['original_info']['width']:
                    thumb = config.server + '/image?url=' + quote_plus(thumb) + '&letterbox=%28640%2C640%29&color=%23444'
                if n == 1:
                    media_html += '<div><a href="{}" target="_blank"><img style="width:100%; border-radius:10px;" src="{}" /></a></div>'.format(img_src, thumb)
                else:
                    gallery_html += '<div style="flex:1; min-width:200px;"><a href="{}" target="_blank"><img src="{}" style="display:block; width:100%; border-radius:10px;" /></a></div>'.format(img_src, thumb)
                    gallery_images.append({"src": img_src, "caption": "", "thumb": thumb})
        if n > 1:
            gallery_html += '</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            media_html += gallery_html
            media_html += '<div style="padding:8px; font-size:0.9em;"><a href="{}" target="_blank">View photo gallery</a></div>'.format(gallery_url)

    # n = 0
    # if tweet_json.get('photos'):
    #     n += len(tweet_json['photos'])
    # if tweet_json.get('video'):
    #     n += 1
    # gallery_images = []
    # gallery_html = ''
    # if n > 1:
    #     gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
    #
    # if tweet_json.get('photos'):
    #     for photo in tweet_json['photos']:
    #         img_src = photo['url']
    #         thumb = img_src + '?format=jpg&name=small'
    #         if n == 1:
    #             media_html += '<div><a href="{}" target="_blank"><img style="width:100%; border-radius:10px;" src="{}" /></a></div>'.format(img_src, thumb)
    #         else:
    #             gallery_html += '<div style="flex:1; min-width:200px;"><a href="{}" target="_blank"><img src="{}" style="display:block; width:100%; border-radius:10px;" /></a></div>'.format(img_src, thumb)
    #             gallery_images.append({"src": img_src, "caption": "", "thumb": thumb})
    #
    # if tweet_json.get('video'):
    #     if tweet_json['video'].get('variants'):
    #         video = next((it for it in tweet_json['video']['variants'] if it['type'].lower() == 'application/x-mpegurl'), None)
    #         if not video:
    #             videos = []
    #             for it in tweet_json['video']['variants']:
    #                 if it['type'] == 'video/mp4':
    #                     m = re.search(r'/(\d+)x(\d+)/', it['src'])
    #                     if m:
    #                         videos.append({
    #                             "src": it['src'],
    #                             "type": it['type'],
    #                             "width": m.group(1),
    #                             "height": m.group(2),
    #                         })
    #             if videos:
    #                 video = utils.closest_dict(videos, 'width', 640)
    #             else:
    #                 video = [it for it in tweet_json['video']['variants'] if it['type'] == 'video/mp4'][-1]
    #         if video:
    #             if video['type'] == 'video/mp4':
    #                 video_src = video['src']
    #             else:
    #                 video_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(video['src']), quote_plus(video['type']), quote_plus(tweet_json['video']['poster']))
    #             thumb = config.server + '/image?url=' + quote_plus(tweet_json['video']['poster'] + '?format=jpg&name=small')
    #             if tweet_json['video'].get('aspectRatio'):
    #                 if tweet_json['video']['aspectRatio'][0] < tweet_json['video']['aspectRatio'][1]:
    #                     thumb += '&letterbox=%28640%2C640%29&color=%23444'
    #             thumb += '&overlay=video'
    #             if n == 1:
    #                 media_html += '<div><a href="{}" target="_blank"><img style="width:100%; border-radius:10px;" src="{}" /></a></div>'.format(video_src, thumb)
    #             else:
    #                 gallery_html += '<div style="flex:1; min-width:200px;"><a href="{}" target="_blank"><img src="{}" style="display:block; width:100%; border-radius:10px;" /></a></div>'.format(video_src, thumb)
    #                 gallery_images.append({"src": video_src, "caption": "", "thumb": thumb})
    #         else:
    #             logger.warning('unhandled video variants')
    #     else:
    #         video_url = entities['media'][0]['expanded_url']
    #         poster = '{}/image?url={}&width=500&overlay=video'.format(config.server, tweet_json['video']['poster'])
    #         media_html += utils.add_image(poster, '', link=video_url, img_style='border-radius:10px;')
    #
    # if n > 1:
    #     gallery_html += '</div>'
    #     gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
    #     media_html += gallery_html
    #     media_html += '<div style="padding:8px; font-size:0.9em;"><a href="{}" target="_blank">View photo gallery</a></div>'.format(gallery_url)

    def replace_spaces(matchobj):
        sp = ''
        for n in range(len(matchobj.group(0))):
            sp += '&nbsp;'
        return sp

    text_html = re.sub(r' {2,}', replace_spaces, text_html)
    text_html = text_html.replace('\n', '<br />')
    text_html = text_html.strip()
    while text_html.endswith('<br />'):
        text_html = text_html[:-6]

    tweet_article = None
    if tweet_json.get('text') and tweet_json['text'].startswith('https://t.co/'):
        entity = next((it for it in tweet_json['entities']['urls'] if it['url'] == tweet_json['text']), None)
        if entity and '/article/' in entity['expanded_url']:
            logger.debug('content is an article')
            tweet_detail = get_tweet_result_by_api('https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_json['id_str']))
            utils.write_file(tweet_detail, './debug/article.json')
            try:
                tweet_article = tweet_detail['data']['tweetResult']['result']['article']['article_results']['result']
            except:
                tweet_article = None
    if tweet_article:
        text_html = make_article(tweet_article)

    if tweet_json.get('card'):
        media_html += make_card(tweet_json['card'], tweet_json)

    dt = datetime.fromisoformat(tweet_json['created_at'].replace('Z', '+00:00'))
    tweet_time = '{}:{:02d} {}'.format(dt.strftime('%I').lstrip('0'), dt.minute, dt.strftime('%p'))
    tweet_date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    if tweet_json.get('quoted_tweet'):
        quoted_html += make_tweet(tweet_json['quoted_tweet'], ref_tweet_url, is_quoted=True)

    if tweet_json.get('birdwatch_pivot'):
        media_html += '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; padding:0.5em;">'
        if tweet_json['birdwatch_pivot'].get('title'):
            media_html += '<div style="margin-bottom:0.5em;"><strong>{}</strong></div>'.format(tweet_json['birdwatch_pivot']['title'])
        if tweet_json['birdwatch_pivot'].get('subtitle'):
            media_html += '<div style="margin-bottom:0.5em;">' + replace_birdwatch_entities(tweet_json['birdwatch_pivot']['subtitle']).replace('\n', '<br/>') + '</div>'
        if tweet_json['birdwatch_pivot'].get('footer'):
            media_html += '<div><small>' + replace_birdwatch_entities(tweet_json['birdwatch_pivot']['footer']).replace('\n', '<br/>') + '</small></div>'
        media_html += '</div>'

    if tweet_json['user']['verified'] == True or tweet_json['user']['is_blue_verified'] == True:
        verified_icon = ' &#9989;'
    else:
        verified_icon = ''

    tweet_url = 'https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_json['id_str'])
    if has_parent:
        logo = ''
    else:
        # logo = '<a href="{}"><img src="https://abs.twimg.com/responsive-web/client-web/icon-ios.77d25eba.png" style="width:100%;"/></a>'.format(ref_tweet_url)
        # https://simpleicons.org/?q=twitter
        logo = '<a href="' + ref_tweet_url + '"><img src="data:image/svg+xml;utf8,<svg role=\'img\' viewBox=\'0 0 24 24\' xmlns=\'http://www.w3.org/2000/svg\'><title>X</title><path d=\'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z\'/></svg>" style="width:100%;"/></a>'

    if is_parent or is_reply:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        if is_reply == 1:
            border = ''
        else:
            border = ' border-left:2px solid rgb(196, 207, 214);'
        tweet_html = '<tr style="font-size:0.95em;"><td style="width:56px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1}</small></a> · <a style="text-decoration:none;" href="{4}"><small>{5}</small></a></td><td style="width:32px;">{6}</td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon, tweet_url, tweet_date, logo)
        tweet_html += '<tr><td colspan="3" style="padding:0 0 0 24px;">'
        # tweet_html += '<table style="font-size:0.95em; padding:0 0 0 24px;{}"><tr><td rowspan="3">&nbsp;</td><td>{}</td></tr>'.format(border, text_html)
        tweet_html += '<table style="font-size:0.95em; padding:0 0 0 24px;{}">'.format(border)
        tweet_html += '<tr><td style="padding:1em 0 0 0;">{}</td></tr>'.format(text_html)
        if media_html:
            tweet_html += '<tr><td style="padding:1em 0 0 0;">{}</td></tr>'.format(media_html)
        if quoted_html:
            tweet_html += '<tr><td style="padding:1em 0 0 0;">{}</td></tr>'.format(quoted_html)
        tweet_html += '<tr><td>&nbsp;</td></tr></table></td></tr>'
    elif is_quoted:
        avatar = '{}/image?url={}&width=32&height=32&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        tweet_html = '<table style="font-size:0.95em; width:100%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#333,#ccc); border-radius:10px;"><tr><td style="width:36px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1} · <a style="text-decoration:none;" href="{4}">{5}</a></small></a></td><td></td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon, tweet_url, tweet_date)
        tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(text_html)
        if media_html:
            tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(media_html)
        if quoted_html:
            tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(quoted_html)
        tweet_html += '</table>'
    else:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        tweet_html = '<tr><td style="width:56px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3}<br /><small>@{1}</small></a></td><td style="width:32px;">{4}</td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon, logo)
        tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(text_html)
        if media_html:
            tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(media_html)
        if quoted_html:
            tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;">{}</td></tr>'.format(quoted_html)
        tweet_html += '<tr><td colspan="3" style="padding:1em 0 0 0;"><a style="text-decoration:none;" href="{}"><small>{} · {}</small></a></td></tr>'.format(tweet_url, tweet_time, tweet_date)

    return tweet_html


def get_tweet_json(tweet_id):
    num = int(tweet_id) / 1e15 * math.pi
    n = 8
    m = re.search(r'e-(\d+)$', str(num))
    if m:
        n += int(m.group(1)) + 1
    number = basencode.Number('{:.30f}'.format(num))
    token = number.repr_in_base(36, max_frac_places=n)
    token = re.sub(r'(0+|\.)', '', token)
    tweet_url = 'https://cdn.syndication.twimg.com/tweet-result?features=tfw_timeline_list%3A%3Btfw_follower_count_sunset%3Atrue%3Btfw_tweet_edit_backend%3Aon%3Btfw_refsrc_session%3Aon%3Btfw_fosnr_soft_interventions_enabled%3Aon%3Btfw_mixed_media_15897%3Atreatment%3Btfw_experiments_cookie_expiration%3A1209600%3Btfw_show_birdwatch_pivots_enabled%3Aon%3Btfw_duplicate_scribes_to_settings%3Aon%3Btfw_use_profile_image_shape_enabled%3Aon%3Btfw_video_hls_dynamic_manifests_15082%3Atrue_bitrate%3Btfw_legacy_timeline_sunset%3Atrue%3Btfw_tweet_edit_frontend%3Aon&id={}&lang=en&token={}'.format(tweet_id, token)
    #print(tweet_url)
    #tweet_url = 'https://cdn.syndication.twimg.com/tweet-result?id={}&lang=en&token=0'.format(tweet_id)
    return utils.get_url_json(tweet_url)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'threadreaderapp' in split_url.netloc:
        tweet_id = paths[-1].replace('.html', '')
    else:
        tweet_id = paths[2]
    if not tweet_id.isnumeric():
        logger.warning('error determining tweet id in ' + url)

    tweet_json = get_tweet_json(tweet_id)
    if not tweet_json:
        return None
    if save_debug:
        utils.write_file(tweet_json, './debug/twitter.json')

    if tweet_json.get('tombstone'):
        # https://twitter.com/gerald1064/status/1537123311041355776
        item = {}
        item['id'] = tweet_id
        item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#333,#ccc); border-radius:10px;"><tr><td style="text-align:center;">{}</td></tr></table><div>&nbsp;</div>'.format(replace_tombstone_entities(tweet_json['tombstone']['text']))
        return item

    if 'screen_name' in tweet_json['user']:
        tweet_user = tweet_json['user']['screen_name']
    else:
        tweet_user = paths[0]

    # content_html = '<table style="width:80%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
    content_html = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'

    item = {}
    item['id'] = tweet_id
    item['url'] = '{}://{}/{}/status/{}'.format(split_url.scheme, split_url.netloc, tweet_user, tweet_id)
    item['author'] = {}
    item['author']['name'] = tweet_user

    if tweet_json['id_str'] != tweet_id:
        # Retweet
        item['title'] = '{} retweeted: {}'.format(tweet_user, tweet_json['text'])
        content_html += '<tr><td colspan="3"><small>&#128257;&nbsp;<a style="text-decoration:none;" href="https://twitter.com/{0}">@{0}</a> retweeted</small></td></tr>'.format(tweet_user)

        # Get the real tweet so we can get the reply thread
        tweet_json = get_tweet_json(tweet_json['id_str'])
        if save_debug:
            utils.write_file(tweet_json, './debug/twitter.json')
        tweet_id = tweet_json['id_str']
        tweet_user = tweet_json['user']['screen_name']
    else:
        item['title'] = '{} tweeted: {}'.format(tweet_user, tweet_json['text'])

    if len(item['title']) > 50:
        item['title'] = item['title'][:50] + '...'

    dt = datetime.fromisoformat(tweet_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['tags'] = []
    if tweet_json.get('entities'):
        if tweet_json['entities'].get('hashtags'):
            for it in tweet_json['entities']['hashtags']:
                item['tags'].append('#{}'.format(it['text']))
        if tweet_json['entities'].get('user_mentions'):
            for it in tweet_json['entities']['user_mentions']:
                item['tags'].append('@{}'.format(it['screen_name']))
        if tweet_json['entities'].get('symbols'):
            for it in tweet_json['entities']['symbols']:
                item['tags'].append('${}'.format(it['text']))
    if len(item['tags']) == 0:
        del item['tags']

    item['summary'] = tweet_json['text']

    tweet_thread = []
    if tweet_json.get('parent'):
        parent = get_tweet_json(tweet_json['parent']['id_str'])
        while parent:
            tweet_thread.insert(0, parent)
            if parent.get('parent'):
                parent = get_tweet_json(parent['parent']['id_str'])
            else:
                parent = None
        for parent in tweet_thread:
            content_html += make_tweet(parent, item['url'], is_parent=True, has_parent=True)

    # tweet_thread.append(tweet_json)
    content_html += make_tweet(tweet_json, item['url'], has_parent=False)

    # Check threadreader to see if there are any "reply" tweets (we should have a all previous "parent" tweets in the thread)
    if 'threadreader' not in args:
        tr_json = utils.get_url_json('https://threadreaderapp.com/api/v0/ping/{}.json'.format(tweet_json['id_str']))
        if tr_json and tr_json['code'] == 200:
            logger.debug('Getting tweet thread')
            tr_html = utils.get_url_html('https://threadreaderapp.com/thread/{}.html'.format(tweet_json['id_str']))
            if tr_html:
                soup = BeautifulSoup(tr_html, 'lxml')
                threads = soup.find_all(class_='content-tweet', attrs={"data-tweet": True})
                if threads:
                    skip_thread = True
                    for thread in threads:
                        if not skip_thread:
                            thread_json = get_tweet_json(thread['data-tweet'])
                            content_html += make_tweet(thread_json, item['url'], is_reply=2, has_parent=True)
                        if thread['data-tweet'] == tweet_id:
                            skip_thread = False

    content_html += '</table><div>&nbsp;</div>'
    item['content_html'] = content_html
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'rsshub.app' and 'twitter' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    elif split_url.netloc == 'twitter.com' and len(paths) == 1:
        feed_url = 'https://rsshub.app/twitter/user/' + paths[0]
        logger.debug('getting twitter feed from ' + feed_url)
        return rss.get_feed(feed_url, args, site_json, save_debug, get_content)
    return None


def get_tweet_result_by_api(tweet_url):
    logger.debug('get_tweet_result_by_api:' + tweet_url)
    r = curl_cffi_requests.get(tweet_url + '?mx=2', impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text

    # extract the guest token
    m = re.search(r'document\.cookie="gt=(\d+)', page_html)
    if not m:
        logger.warning('unable to determine guest token for ' + tweet_url)
        return None
    guest_token = m.group(1)
    logger.debug('using guest token ' + guest_token)

    # Bearer tokens are in the main.xxxxxxx.js script
    m = re.search(r'https://[^/]+/responsive-web/client-web/main\.[a-f0-9]+\.js', page_html)
    if not m:
        logger.warning('unable to determine main.js script in ' + tweet_url)
        return None
    r = curl_cffi_requests.get(m.group(0), impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    main_js = r.text
    auth_tokens = re.findall(r'Bearer[^"]+', main_js)
    if not auth_tokens:
        logger.warning('unable to determine Bearer tokens in ' + m.group(0))
        return None

    variables = {
        "tweetId": tweet_url.split('/')[-1],
        "withCommunity": False,
        "includePromotedContent": False,
        "withVoice": False
    }
    features = {
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_enhance_cards_enabled": False
    }
    field_toggles = {
        "withArticleRichContentState": True,
        "withArticlePlainText": False,
        "withGrokAnalyze": False,
        "withDisallowedReplyControls": False
    }
    api_url = 'https://api.x.com/graphql/sCU6ckfHY0CyJ4HFjPhjtg/TweetResultByRestId?variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&features=' + quote_plus(json.dumps(features, separators=(',', ':'))) + '&fieldToggles=' + quote_plus(json.dumps(field_toggles, separators=(',', ':')))
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "priority": "u=1, i",
        "x-guest-token": guest_token,
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en"
    }
    for token in reversed(auth_tokens):
        logger.debug('trying twitter auth token ' + token)
        headers['authorization'] = token
        r = curl_cffi_requests.get(api_url, headers=headers, impersonate=config.impersonate, proxies=config.proxies)
        if r and r.status_code == 200:
            utils.write_file(r.json(), './debug/tweet-api.json')
            return r.json()
        if r:
            logger.debug('TweetResultByRestId status code {}'.format(r.status_code))
        else:
            logger.debug('TweetResultByRestId failed')

    # x-client-transaction-id doesn't seem necessary
    # Here's details on reverse engineering: https://antibot.blog/twitter/
    # https://github.com/obfio/twitter-tid-script-cleaned/blob/main/cleaned.js
    # https://github.com/laszlovandenhoek/twitter-scraper/blob/7e074a5e409a0501d292404304d0419d5367375f/getbookmarks.py
    # https://github.com/dimdenGD/OldTwitter/blob/535b762525ceb888003f90aa92dfdcdc10e5a237/scripts/twchallenge.js
    # random_data = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=70))
    # transaction_id = base64.urlsafe_b64encode(random_data.encode()).decode().replace('=', '')
    return None

# https://twitter.com/tracewoodgrains/status/1783701072894193994

# url = "https://api.twitter.com/1.1/onboarding/sso_init.json"
# headers = {
#     "accept": "*/*",
#     "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
#     "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
#     "content-type": "application/json",
#     "priority": "u=1, i",
#     "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
#     "sec-ch-ua-mobile": "?0",
#     "sec-ch-ua-platform": "\"Windows\"",
#     "sec-fetch-dest": "empty",
#     "sec-fetch-mode": "cors",
#     "sec-fetch-site": "same-site",
#     "x-client-transaction-id": "ceHMt/cd9On9gzaRO3YfLsH591H/fJ9atbV6hycxmr4XR32l3tnnEbleWT+nR9CavbJyhnBCldKFi1V15EaqeOKnxZJRcg",
#     "x-guest-token": "1791183215345991843",
#     "x-twitter-active-user": "yes",
#     "x-twitter-client-language": "en"
# }
# body = {"provider": "apple"}
