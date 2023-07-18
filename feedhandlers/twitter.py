import json, random, re, requests, string
from datetime import datetime
from urllib.parse import quote_plus, unquote, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


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
            card_html = '<figure style="width:100%; margin:0; padding:0; border:1px solid black; border-radius:10px;">'
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
        else:
            logger.warning('unhandled unified card type ' + unified_card['type'])

    elif 'event' in card_json['name']:
        card_type = 2
        card_link = get_expanded_url(tweet_json, card_json['url'])
        title = binding_values['event_title']['string_value']
        card_desc = binding_values['event_subtitle']['string_value']
        img = binding_values['event_thumbnail']['image_value']['url']

    elif re.search('poll\dchoice_text_only', card_json['name']):
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
            pct = int(count / total_count * 100)
            if pct >= 50:
                card_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, {} {}%, white {}%);"><p{}>{}</p><p{}>{}%</p></div>'.format(color, pct, 100 - pct, style, label, style, pct)
            else:
                card_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, {} {}%);"><p{}>{}</p><p{}>{}%</p></div>'.format(100 - pct, color, pct, style, label, style, pct)
        card_html += '</div><div><small>'
        if binding_values['counts_are_final']['boolean_value'] == True:
            card_html += 'Final results'
        else:
            card_html += 'Polling in progress'
        card_html += '&nbsp;&bull;&nbsp;{} votes'.format(total_count)
        dt = datetime.fromisoformat(
            binding_values['last_updated_datetime_utc']['string_value'].replace('Z', '+00:00'))
        card_html += '&nbsp;&bull;&nbsp;Last updated {}</small></div>'.format(utils.format_display_date(dt, False))

    elif card_json['name'] == 'promo_website':
        card_type = 2
        card_link = binding_values['website_dest_url']['string_value']
        title = binding_values['title']['string_value']
        img = binding_values['promo_image']['image_value']['url']

    elif 'promo_video_website' in card_json['name']:
        # Only shows the image not the promo video
        card_type = 2
        card_link = binding_values['website_dest_url']['string_value']
        title = binding_values['title']['string_value']
        img = binding_values['player_image']['image_value']['url']

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
        card_html += '<table style="margin:0; padding:0; border:1px solid black; border-radius:10px; border-spacing:0;"><tr>'
        card_html += '<td style="line-height:0; width:128px; height:128px; padding:0 8px 0 0; border-collapse:collapse;"><a href="{}">{}</a></td>'.format(img_link, img)
        card_html += '<td style="padding:0; border-collapse:collapse; vertical-align:top;"><div style="max-height:128px; overflow:hidden;"><small>{}</small><br/><a href="{}"><b>{}</b></a><br/>{}</div></td>'.format(link_text, card_link, title, card_desc)
        card_html += '</tr></table>'

    elif card_type == 2:
        desc = '<div style="margin:8px;"><small>{}</small><br/><a href="{}"><b>{}</b></a><br/>{}</div>'.format(link_text, card_link, title, card_desc)
        card_html += utils.add_image(img_src, '', link=card_link, img_style="border-top-left-radius:10px; border-top-right-radius:10px;", fig_style="margin:0; padding:0; border:1px solid black; border-radius:10px;", desc=desc)
    return card_html


def make_tweet(tweet_json, is_parent=False, is_quoted=False, is_reply=0):
    media_html = ''
    text_html = tweet_json['text'].strip()

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

    if tweet_json['entities'].get('media'):
        for media in tweet_json['entities']['media']:
            text_html = text_html.replace(media['url'], '')

    if tweet_json['entities'].get('urls'):
        for url in tweet_json['entities']['urls']:
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

    if tweet_json.get('photos'):
        for photo in tweet_json['photos']:
            media_html += '<div><a href="{0}"><img width="100%" style="border-radius:10px" src="{0}" /></a></div>'.format(photo['url'])

    if tweet_json.get('video'):
        if tweet_json['video'].get('variants'):
            for video in tweet_json['video']['variants']:
                if 'mp4' in video['type']:
                    media_html += utils.add_video(video['src'], 'video/mp4', tweet_json['video']['poster'], img_style='border-radius:10px;')
                    break
        else:
            video_url = tweet_json['entities']['media'][0]['expanded_url']
            poster = '{}/image?url={}&width=500&overlay=video'.format(config.server, tweet_json['video']['poster'])
            media_html += utils.add_image(poster, '', link=video_url, img_style='border-radius:10px;')

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

    if tweet_json.get('card'):
        media_html += make_card(tweet_json['card'], tweet_json)

    dt = datetime.fromisoformat(tweet_json['created_at'].replace('Z', '+00:00'))
    tweet_time = '{}:{} {}'.format(dt.strftime('%I').lstrip('0'), dt.minute, dt.strftime('%p'))
    tweet_date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    if tweet_json.get('quoted_tweet'):
        media_html += make_tweet(tweet_json['quoted_tweet'], is_quoted=True)

    if tweet_json['user']['verified'] == True:
        verified_icon = ' &#9989;'
    else:
        verified_icon = ''

    tweet_url = 'https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_json['id_str'])

    if is_parent or is_reply:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        border = ' border-left:2px solid rgb(196, 207, 214);'
        if is_reply == 1:
            border = ''
        tweet_html = '<tr style="font-size:0.9em;"><td style="width:56px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1} · <a style="text-decoration:none;" href="{4}">{5}</a></small></a></td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon, tweet_url, tweet_date)
        tweet_html += '<tr><td colspan="2" style="padding:0 0 0 24px;">'
        tweet_html += '<table style="font-size:0.9em; padding:0 0 0 24px;{}"><tr><td rowspan="3">&nbsp;</td><td>{}</td></tr>'.format(border, text_html)
        tweet_html += '<tr><td>{}</td></tr></table></tr></td>'.format(media_html)
    elif is_quoted:
        avatar = '{}/image?url={}&width=32&height=32&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        tweet_html = '<table style="font-size:0.9em; width:95%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;"><tr><td style="width:36px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1} · <a style="text-decoration:none;" href="{4}">{5}</a></small></a></td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon, tweet_url, tweet_date)
        tweet_html += '<tr><td colspan="2">{}</td></tr>'.format(text_html)
        tweet_html += '<tr><td colspan="2">{}</td></tr></table>'.format(media_html)
    else:
        avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(tweet_json['user']['profile_image_url_https']))
        tweet_html = '<tr><td style="width:56px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3}<br /><small>@{1}</small></a></td></tr>'.format(
            avatar, tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_icon)
        tweet_html += '<tr><td colspan="2" style="padding:0 0 1em 0;">{}</td></tr>'.format(text_html)
        tweet_html += '<tr><td colspan="2">{}</td></tr>'.format(media_html)
        tweet_html += '<tr><td colspan="2"><a style="text-decoration:none;" href="{}"><small>{} · {}</small></a></td></tr>'.format(tweet_url, tweet_time, tweet_date)

    return tweet_html


def get_tweet_json(tweet_id):
    return utils.get_url_json('https://cdn.syndication.twimg.com/tweet-result?id={}&lang=en'.format(tweet_id))


def get_content(url, args, site_json, save_debug=False):
    tweet_id = ''
    tweet_user = ''
    clean_url = ''

    # url can be just the id
    if url.startswith('https'):
        clean_url = utils.clean_url(url)
        m = re.search('twitter\.com/([^/]+)/statuse?s?/(\d+)', clean_url)
        if m:
            tweet_user = m.group(1)
            tweet_id = m.group(2)
        else:
            logger.warning('error determining tweet id in ' + url)
            return None
    elif url.isnumeric():
        tweet_id = url

    if False:
        session = requests.Session()
        r = session.get(url)
        print(r.status_code)
        if r.status_code == 200:
            cookies = session.cookies.get_dict()
            if cookies.get('guest_id'):
                guest_id = unquote(cookies['guest_id']).split(':')[-1]
                headers = {
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9",
                    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                    "cache-control": "no-cache",
                    "content-type": "application/json",
                    "pragma": "no-cache",
                    "sec-ch-ua": "\"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"114\", \"Microsoft Edge\";v=\"114\"",
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": "\"Windows\"",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "x-csrf-token": ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                    "x-guest-token": guest_id,
                    "x-twitter-active-user": "yes",
                    "x-twitter-client-language": "en"
                }
                api_url = 'https://twitter.com/i/api/graphql/2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId?variables=%7B%22tweetId%22%3A%22{}%22%2C%22withCommunity%22%3Afalse%2C%22includePromotedContent%22%3Afalse%2C%22withVoice%22%3Afalse%7D&features=%7B%22creator_subscriptions_tweet_preview_api_enabled%22%3Atrue%2C%22tweetypie_unmention_optimization_enabled%22%3Atrue%2C%22responsive_web_edit_tweet_api_enabled%22%3Atrue%2C%22graphql_is_translatable_rweb_tweet_is_translatable_enabled%22%3Atrue%2C%22view_counts_everywhere_api_enabled%22%3Atrue%2C%22longform_notetweets_consumption_enabled%22%3Atrue%2C%22responsive_web_twitter_article_tweet_consumption_enabled%22%3Afalse%2C%22tweet_awards_web_tipping_enabled%22%3Afalse%2C%22freedom_of_speech_not_reach_fetch_enabled%22%3Atrue%2C%22standardized_nudges_misinfo%22%3Atrue%2C%22tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled%22%3Atrue%2C%22longform_notetweets_rich_text_read_enabled%22%3Atrue%2C%22longform_notetweets_inline_media_enabled%22%3Atrue%2C%22responsive_web_graphql_exclude_directive_enabled%22%3Atrue%2C%22verified_phone_label_enabled%22%3Afalse%2C%22responsive_web_media_download_video_enabled%22%3Afalse%2C%22responsive_web_graphql_skip_user_profile_image_extensions_enabled%22%3Afalse%2C%22responsive_web_graphql_timeline_navigation_enabled%22%3Atrue%2C%22responsive_web_enhance_cards_enabled%22%3Afalse%7D&fieldToggles=%7B%22withArticleRichContentState%22%3Afalse%7D'.format(tweet_id)
                print(api_url)
                r = session.get(api_url, headers=headers)
                print(r.status_code)
                if r.status_code == 200:
                    utils.write_file(r.json, './debug/twitter_api.json')

    tweet_json = get_tweet_detail(tweet_id)
    if tweet_json:
        utils.write_file(tweet_json, './debug/tweet.json')

    tweet_json = get_tweet_json(tweet_id)
    if not tweet_json:
        return None
    if save_debug:
        utils.write_file(tweet_json, './debug/twitter.json')

    if not clean_url:
        tweet_user = tweet_json['user']['screen_name']
        clean_url = 'https://twitter.com/{}/status/{}'.format(tweet_user, tweet_id)

    # content_html = '<table style="width:80%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
    content_html = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'

    item = {}
    item['id'] = tweet_id
    item['url'] = clean_url
    item['author'] = {}
    item['author']['name'] = tweet_user

    if not tweet_json['id_str'] in clean_url:
        # Retweet
        item['title'] = '{} retweeted: {}'.format(tweet_user, tweet_json['text'])
        content_html += '<tr><td colspan="2"><small>&#128257;&nbsp;<a style="text-decoration:none;" href="https://twitter.com/{0}">@{0}</a> retweeted</small></td></tr>'.format(tweet_user)

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
            content_html += make_tweet(parent, is_parent=True)

    tweet_thread.append(tweet_json)

    content_html += make_tweet(tweet_json)

    if False:
        # Find the conversation thread (replies from the same user)
        search_scraper = None
        try:
            query = 'from:{} conversation_id:{} (filter:safe OR -filter:safe)'.format(tweet_user, tweet_id)
            search_scraper = sntwitter.TwitterSearchScraper(query)
        except Exception as e:
            logger.warning('TwitterSearchScraper exception {} in {}'.format(e.__class__, clean_url))

        if search_scraper:
            try:
                tweet_replies = []
                for i, tweet in enumerate(search_scraper.get_items()):
                    tweet_json = get_tweet_json(tweet.id)
                    if tweet_json.get('in_reply_to_screen_name') and tweet_json['in_reply_to_screen_name'] == tweet_user:
                        tweet_replies.append(tweet_json)
                for i, tweet_json in reversed(list(enumerate(tweet_replies))):
                    content_html += make_tweet(tweet_json, is_reply=i + 1)
            except Exception as e:
                logger.warning('TwitterSearchScraper.get_items exception {} in {}'.format(e.__class__, clean_url))

    content_html += '</table><br/>'
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
