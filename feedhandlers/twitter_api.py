import base64, json, pytz, re, requests
import dateutil.parser
from bs4 import BeautifulSoup
from requests_oauthlib import OAuth1
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import twitter

import logging

logger = logging.getLogger(__name__)

TW_CONSUMER_KEY = '3nVuSoBZnx6U4vzUxf5w'
TW_CONSUMER_SECRET = 'Bcs59EFbbsdF6Sl9Ng71smgStWEGwXXKSjYvPVt7qys'

gql_features = {
    "android_graphql_skip_api_media_color_palette": False,
    "blue_business_profile_image_shape_enabled": False,
    "creator_subscriptions_subscription_count_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": False,
    "hidden_profile_likes_enabled": False,
    "highlights_tweets_tab_ui_enabled": False,
    "interactive_text_enabled": False,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "longform_notetweets_richtext_consumption_enabled": True,
    "longform_notetweets_rich_text_read_enabled": False,
    "responsive_web_edit_tweet_api_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": False,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_text_conversations_enabled": False,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "responsive_web_twitter_blue_verified_badge_is_enabled": True,
    "rweb_lists_timeline_redesign_enabled": True,
    "spaces_2022_h2_clipping": True,
    "spaces_2022_h2_spaces_communities": True,
    "standardized_nudges_misinfo": False,
    "subscriptions_verification_info_enabled": True,
    "subscriptions_verification_info_reason_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "super_follow_badge_privacy_enabled": False,
    "super_follow_exclusive_tweet_notifications_enabled": False,
    "super_follow_tweet_api_enabled": False,
    "super_follow_user_api_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
    "tweetypie_unmention_optimization_enabled": False,
    "unified_cards_ad_metadata_container_dynamic_card_content_query_enabled": False,
    "verified_phone_label_enabled": False,
    "vibe_api_enabled": False,
    "view_counts_everywhere_api_enabled": False
}


def get_card(url, card):
    title = ''
    description = ''
    domain = ''
    caption = ''
    img_src = ''
    card_url = ''
    if card.get('binding_values'):
        val = next((it for it in card['binding_values'] if it['key'] == 'unified_card'), None)
        if val:
            # https://twitter.com/Arsenal/status/1541360730225745920
            # https://twitter.com/WEURO/status/1653368030037004288
            unified_card = json.loads(val['value']['string_value'])
            utils.write_file(unified_card, './debug/card.json')
            for key in unified_card['components']:
                component = unified_card['component_objects'][key]
                if component['type'] == 'media':
                    media = unified_card['media_entities'][component['data']['id']]
                    if media['type'] == 'animated_gif' or media['type'] == 'video':
                        videos = []
                        for it in media['video_info']['variants']:
                            if it['content_type'] == 'video/mp4':
                                videos.append(it)
                        video = utils.closest_dict(videos, 'bitrate', 1000000)
                        card_url = video['url']
                        img_src = '{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(media['media_url_https']))
                    elif media['type'] == 'photo':
                        img_src = media['media_url_https']
                    else:
                        logger.warning('unhandled extended media type ' + media['type'])
                elif component['type'] == 'details':
                    if component['data'].get('subtitle'):
                        caption = '<div style="margin-left:8px;">{}</div>'.format(component['data']['subtitle']['content'])
                    if component['data'].get('title'):
                        if component['data'].get('destination'):
                            dest = unified_card['destination_objects'][component['data']['destination']]
                            dest_url = dest['data']['url_data']['url']
                            description = '<div style="margin:8px;"><a href="{}">{}</a></div>'.format(dest_url, component['data']['title']['content'])
                        else:
                            description = '<div style="margin:8px;">{}</div>'.format(component['data']['title']['content'])
            if img_src:
                #print(caption, description)
                return utils.add_image(img_src, caption, link=card_url,
                                        img_style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;",
                                        fig_style="margin:0; padding:0; border:1px solid black; border-radius:10px;",
                                        desc=description)
            else:
                logger.warning('unhandled unified_card')
                return ''
        if isinstance(card['binding_values'], list):
            val = next((it for it in card['binding_values'] if it['key'] == 'title'), None)
            if val:
                title = val['value']['string_value']
            val = next((it for it in card['binding_values'] if it['key'] == 'description'), None)
            if val:
                description = val['value']['string_value']
            val = next((it for it in card['binding_values'] if it['key'] == 'domain'), None)
            if val:
                domain = val['value']['string_value']
            if card['name'] == 'player':
                val = next((it for it in card['binding_values'] if it['key'] == 'player_image_original'), None)
                if val:
                    img_src = val['value']['image_value']['url']
            else:
                val = next((it for it in card['binding_values'] if it['key'] == 'photo_image_full_size_original'), None)
                if val:
                    img_src = val['value']['image_value']['url']
                else:
                    val = next((it for it in card['binding_values'] if it['key'] == 'thumbnail_image_original'), None)
                    if val:
                        img_src = val['value']['image_value']['url']
        elif isinstance(card['binding_values'], dict):
            if card['binding_values'].get('title'):
                title = card['binding_values']['title']['string_value']
            if card['binding_values'].get('description'):
                description = card['binding_values']['description']['string_value']
            if card['binding_values'].get('domain'):
                domain = card['binding_values']['domain']['string_value']
            if card['name'] == 'player':
                if card['binding_values'].get('player_image_original'):
                    img_src = card['binding_values']['player_image_original']['image_value']['url']
            else:
                if card['binding_values'].get('photo_image_full_size_original'):
                    img_src = card['binding_values']['photo_image_full_size_original']['image_value']['url']
                elif card['binding_values'].get('thumbnail_image_original'):
                    img_src = card['binding_values']['thumbnail_image_original']['image_value']['url']
    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return ''
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('meta', attrs={"name": "twitter:title"})
        if el:
            title = el['content']
        else:
            el = soup.find('meta', attrs={"property": "og:title"})
            if el:
                title = el['content']
            else:
                el = soup.find('title')
                if el:
                    title = el.get_text()
        el = soup.find('meta', attrs={"name": "twitter:description"})
        if el:
            description = el['content']
        else:
            el = soup.find('meta', attrs={"property": "og:description"})
            if el:
                description = el['content']
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            img_src = el['content']
        else:
            el = soup.find('meta', attrs={"name": "twitter:image"})
            if el:
                img_src = el['content']

    split_url = urlsplit(url)
    if split_url.netloc == 'trib.al':
        card_url = utils.get_redirect_url(url)
    else:
        card_url = url

    if not domain:
        domain = urlsplit(card_url).netloc
    domain = re.sub(r'^www\.', '', domain)

    card_html = ''
    if card['name'] == 'summary_large_image' and img_src:
        caption = '<div style="margin-left:8px;">{}</div>'.format(domain)
        desc = '<div style="margin:8px;"><a href="{}"><b>{}</b></a><br/>{}</div>'.format(card_url, title, description)
        card_html = utils.add_image(img_src, caption, link=card_url, img_style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;", fig_style="margin:0; padding:0; border:1px solid black; border-radius:10px;", desc=desc)
    elif card['name'] == 'player' or card['name'] == 'summary' or (card['name'] == 'summary_large_image' and not img_src):
        if img_src:
            img_src = '{}/image?url={}&crop=0&width=128'.format(config.server, quote_plus(img_src))
        else:
            img_src = '{}/image?width=128&height=128'.format(config.server)
        m = re.search(r'^(.{80,}?)\s', description)
        if m:
            description = m.group(1) + '&mldr;'
        #card_html = '<div style="display:flex; flex-wrap:wrap; gap:8px; border:1px solid black; border-radius:10px;">'
        card_html = '<table style="margin:0; padding:0; border:1px solid black; border-radius:10px; border-spacing:0;"><tr>'
        if card['name'] == 'player':
            img_src += '&overlay=video'
            if domain == 'youtube.com':
                video_url = '{}/video?url={}'.format(config.server, quote_plus(card_url))
            else:
                video_url = card_url
            #card_html += '<div style="flex:1; min-width:100px; max-width:128px; height:128px; margin:auto;"><a href="{}"><img style="width:128px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"/></a></div>'.format(video_url, img_src)
            card_html += '<td style="line-height:0; width:128px; height:128px; padding:0 8px 0 0; border-collapse:collapse;"><a href="{}"><img style="width:128px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"/></a></td>'.format(video_url, img_src)
        else:
            #card_html += '<div style="flex:1; min-width:100px; max-width:128px; height:128px; margin:auto;"><a href="{}"><img style="width:128px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"/></a></div>'.format(card_url, img_src)
            card_html += '<td style="line-height:0; width:128px; height:128px; padding:0 8px 0 0; border-collapse:collapse;"><a href="{}"><img style="width:128px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"/></a></td>'.format(card_url, img_src)
        #card_html += '<div style="flex:2; min-width:256px; margin:auto;"><small>{}</small><br/><a href="{}"><b>{}</b></a><br/>{}</div>'.format(domain, card_url, title, description)
        #card_html += '</div>'
        card_html += '<td style="padding:0; border-collapse:collapse; vertical-align:top;"><div style="max-height:128px; overflow:hidden;"><small>{}</small><br/><a href="{}"><b>{}</b></a><br/>{}</div></td>'.format(domain, card_url, title, description)
        card_html += '</tr></table>'
    else:
        logger.warning('unhandled card type ' + card['name'])
    return card_html


def get_guest_account():
    # https://github.com/zedeus/nitter/issues/983#issuecomment-1681199357
    TW_ANDROID_BASIC_TOKEN = 'Basic ' + base64.b64encode((TW_CONSUMER_KEY + ':' + TW_CONSUMER_SECRET).encode('utf-8')).decode('utf-8')

    # Bearer Token
    headers = {
        "Authorization": TW_ANDROID_BASIC_TOKEN,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    r = requests.post('https://api.twitter.com/oauth2/token', headers=headers, data='grant_type=client_credentials')
    if r.status_code != 200:
        logger.warning('Unable to get bearer token')
        return None
    bearer_token = ' '.join(r.json().values())

    # Guest Token
    headers = {
        "Authorization": bearer_token
    }
    r = requests.post('https://api.twitter.com/1.1/guest/activate.json', headers=headers)
    if r.status_code != 200:
        logger.warning('Unable to get guest token')
        return None
    guest_token = r.json()['guest_token']

    # Flow Token
    headers = {
        "Authorization": bearer_token,
        "Content-Type": "application/json",
        "User-Agent": "TwitterAndroid/9.95.0-release.0 (29950000-r-0) ONEPLUS+A3010/9 (OnePlus;ONEPLUS+A3010;OnePlus;OnePlus3;0;;1;2016)",
        "X-Twitter-API-Version": "5",
        "X-Twitter-Client": "TwitterAndroid",
        "X-Twitter-Client-Version": "9.95.0-release.0",
        "OS-Version": "28",
        "System-User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ONEPLUS A3010 Build/PKQ1.181203.001)",
        "X-Twitter-Active-User": "yes",
        "X-Guest-Token": guest_token
    }
    body = '{"flow_token":null,"input_flow_data":{"country_code":null,"flow_context":{"start_location":{"location":"splash_screen"}},"requested_variant":null,"target_user_id":0},"subtask_versions":{"generic_urt":3,"standard":1,"open_home_timeline":1,"app_locale_update":1,"enter_date":1,"email_verification":3,"enter_password":5,"enter_text":5,"one_tap":2,"cta":7,"single_sign_on":1,"fetch_persisted_data":1,"enter_username":3,"web_modal":2,"fetch_temporary_password":1,"menu_dialog":1,"sign_up_review":5,"interest_picker":4,"user_recommendations_urt":3,"in_app_notification":1,"sign_up":2,"typeahead_search":1,"user_recommendations_list":4,"cta_inline":1,"contacts_live_sync_permission_prompt":3,"choice_selection":5,"js_instrumentation":1,"alert_dialog_suppress_client_events":1,"privacy_options":1,"topics_selector":1,"wait_spinner":3,"tweet_selection_urt":1,"end_flow":1,"settings_list":7,"open_external_link":1,"phone_verification":5,"security_key":3,"select_banner":2,"upload_media":1,"web":2,"alert_dialog":1,"open_account":2,"action_list":2,"enter_phone":2,"open_link":1,"show_code":1,"update_users":1,"check_logged_in_account":1,"enter_email":2,"select_avatar":4,"location_permission_prompt":2,"notifications_permission_prompt":4}}'
    r = requests.post('https://api.twitter.com/1.1/onboarding/task.json?flow_name=welcome&api_version=1&known_device_token=&sim_country_code=us', headers=headers, data=body)
    if r.status_code != 200:
        logger.warning('Unable to get flow token')
        return None
    flow_token = r.json()['flow_token']

    # Subtasks
    body = '{"flow_token":"' + flow_token + '","subtask_inputs":[{"open_link":{"link":"next_link"},"subtask_id":"NextTaskOpenLink"}],"subtask_versions":{"generic_urt":3,"standard":1,"open_home_timeline":1,"app_locale_update":1,"enter_date":1,"email_verification":3,"enter_password":5,"enter_text":5,"one_tap":2,"cta":7,"single_sign_on":1,"fetch_persisted_data":1,"enter_username":3,"web_modal":2,"fetch_temporary_password":1,"menu_dialog":1,"sign_up_review":5,"interest_picker":4,"user_recommendations_urt":3,"in_app_notification":1,"sign_up":2,"typeahead_search":1,"user_recommendations_list":4,"cta_inline":1,"contacts_live_sync_permission_prompt":3,"choice_selection":5,"js_instrumentation":1,"alert_dialog_suppress_client_events":1,"privacy_options":1,"topics_selector":1,"wait_spinner":3,"tweet_selection_urt":1,"end_flow":1,"settings_list":7,"open_external_link":1,"phone_verification":5,"security_key":3,"select_banner":2,"upload_media":1,"web":2,"alert_dialog":1,"open_account":2,"action_list":2,"enter_phone":2,"open_link":1,"show_code":1,"update_users":1,"check_logged_in_account":1,"enter_email":2,"select_avatar":4,"location_permission_prompt":2,"notifications_permission_prompt":4}}'
    r = requests.post('https://api.twitter.com/1.1/onboarding/task.json', headers=headers, data=body)
    if r.status_code != 200:
        logger.warning('Unable to get subtasks')
        return None
    guest_account = next((it['open_account'] for it in r.json()['subtasks'] if it['subtask_id'] == 'OpenAccount'), None)
    if not guest_account:
        logger.warning('No OpenAccount found')
    # Save oauth token values in config.py
    # twitter_oauth_token = guest_account['oauth_token']
    # twitter_oauth_token_secret = guest_account['oauth_token_secret']
    return guest_account


def get_tweet_detail(tweet_id, oauth1, by_rest_id=False):
    if not oauth1:
        oauth1 = OAuth1(TW_CONSUMER_KEY, TW_CONSUMER_SECRET, config.twitter_oauth_token, config.twitter_oauth_token_secret, realm='https://api.twitter.com/', signature_type="AUTH_HEADER", signature_method="HMAC-SHA1")

    if by_rest_id:
        variables = {
            "tweetId": tweet_id,
            "withCommunity": False,
            "includePromotedContent": False,
            "withVoice": False
        }
        api_url = 'https://twitter.com/i/api/graphql/sITyJdhRPpvpEjg4waUmTA/TweetResultByIdQuery'
    else:
        variables = {
            "focalTweetId": tweet_id,
            "includeHasBirdwatchNotes": False,
            "includePromotedContent": False,
            "withBirdwatchNotes": False,
            "withVoice": False,
            "withV2Timeline": True
        }
        api_url = 'https://api.twitter.com/graphql/q94uRCEn65LZThakYcPT6g/TweetDetail'
    r = requests.get(api_url, auth=oauth1,
            params={"features": json.dumps(gql_features), "variables": json.dumps(variables)})
    if r.status_code == 200:
        return r.json()
    elif r.status_code == 429:
        logger.warning('status error 429: guest account is being rate limited')
    else:
        logger.warning('status error {} getting TweetDetail'.format(r.status_code))
        return None


def get_user_by_screen_name(screen_name, oauth1):
    variables = {
        "screen_name": screen_name
    }
    r = requests.get("https://api.twitter.com/graphql/u7wQyGi6oExe8_TRWGMq4Q/UserResultByScreenNameQuery", auth=oauth1,
                     params={"features": json.dumps(gql_features), "variables": json.dumps(variables)})
    if r.status_code != 200:
        logger.warning('status error {} getting UserByScreenName'.format(r.status_code))
        return None
    return r.json()


def get_user_by_id(user_id, oauth1):
    variables = {
        "rest_id": user_id
    }
    r = requests.get("https://api.twitter.com/graphql/oPppcargziU1uDQHAUmH-A/UserResultByIdQuery", auth=oauth1,
                     params={"features": json.dumps(gql_features), "variables": json.dumps(variables)})
    if r.status_code != 200:
        logger.warning('status error {} getting UserByScreenName'.format(r.status_code))
        return None
    return r.json()


def get_user_tweets(user_id, oauth1):
    variables = {
        "userId": user_id
    }
    r = requests.get("https://api.twitter.com/graphql/3JNH4e9dq1BifLxAa3UMWg/UserWithProfileTweetsQueryV2", auth=oauth1,
                     params={"features": json.dumps(gql_features), "variables": json.dumps(variables)})
    if r.status_code != 200:
        logger.warning('status error {} getting UserTweetsAndReplies'.format(r.status_code))
        return None
    return r.json()


def get_user_tweets_and_replies(user_id, oauth1):
    variables = {
        "userId": user_id
    }
    r = requests.get("https://api.twitter.com/graphql/8IS8MaO-2EN6GZZZb8jF0g/UserWithProfileTweetsAndRepliesQueryV2", auth=oauth1,
                     params={"features": json.dumps(gql_features), "variables": json.dumps(variables)})
    if r.status_code != 200:
        logger.warning('status error {} getting UserTweetsAndReplies'.format(r.status_code))
        return None
    return r.json()


def get_content(url, args, site_json, save_debug=False):
    tweet_id = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'platform.twitter.com' and 'embed' in paths:
        query = parse_qs(split_url.query)
        if query.get('id'):
            tweet_id = query['id'][0]
    else:
        tweet_id = paths[2]
    if not tweet_id:
        logger.warning('unknown tweet id in ' + url)
        return None

    oauth1 = OAuth1(TW_CONSUMER_KEY, TW_CONSUMER_SECRET, config.twitter_oauth_token, config.twitter_oauth_token_secret, realm='https://api.twitter.com/', signature_type="AUTH_HEADER", signature_method="HMAC-SHA1")
    tweet_json = get_tweet_detail(tweet_id, oauth1)
    if not tweet_json:
        logger.debug('using twitter handler for ' + url)
        return twitter.get_content(url, args, site_json, save_debug)
    if save_debug:
        utils.write_file(tweet_json, './debug/twitter.json')

    item = {}
    parents = ''
    parent_id = ''
    children = ''
    if 'is_retweet' in args:
        is_retweet = True
    else:
        is_retweet = False
    if tweet_json.get('errors'):
        body = 'Something went wrong.'
        if tweet_json['errors'][0].get('message'):
            body += ' {}'.format(tweet_json['errors'][0]['message'])
        if is_retweet:
            item['content_html'] = '<table style="font-size:0.95em; width:100%; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
            item['content_html'] += '<tr><td colspan="2"><div style="text-align:center;">{}</div></td></tr>'.format(body)
            item['content_html'] += '</table>'
        else:
            item['content_html'] = '<tr><td colspan="2"><div style="text-align:center;">{}</div></td></tr>'.format(body)
    else:
        for instruction in tweet_json['data']['threaded_conversation_with_injections_v2']['instructions']:
            if instruction['type'] == 'TimelineAddEntries':
                for entry in instruction['entries']:
                    #print(entry['entryId'])
                    if entry['entryId'].startswith('tweet-'):
                        if entry['content']['itemContent']['tweet_results'].get('result'):
                            tweet_result = entry['content']['itemContent']['tweet_results']['result']
                            if not parent_id:
                                if tweet_result.get('rest_id'):
                                    parent_id = tweet_result['rest_id']
                                else:
                                    parent_id = entry['entryId'].split('-')[-1]
                            if tweet_id in entry['entryId'].split('-'):
                                item = get_tweet(tweet_result, is_retweet=is_retweet)
                            else:
                                it = get_tweet(tweet_result, is_thread=True, is_retweet=is_retweet)
                                if it:
                                    parents += it['content_html']
                        else:
                            if tweet_id in entry['entryId'].split('-'):
                                item['content_html'] = '<tr><td colspan="2"><div style="text-align:center;">Hmm...this post doesn’t exist.</div></td></tr>'
                            else:
                                parents += '<tr><td colspan="2"><div style="text-align:center;">Hmm...this post doesn’t exist.</div></td></tr>'
                    elif entry['entryId'].startswith('conversationthread-'):
                        for content_item in entry['content']['items']:
                            if content_item['item']['itemContent']['__typename'] == 'TimelineTweet':
                                if content_item['item']['itemContent']['tweet_results'].get('result'):
                                    tweet_result = content_item['item']['itemContent']['tweet_results']['result']
                                    if tweet_result['__typename'] == 'Tweet' and tweet_result['legacy'].get('self_thread') and tweet_result['legacy']['self_thread']['id_str'] == parent_id:
                                        it = get_tweet(tweet_result, is_thread=True)
                                        if it:
                                            children += it['content_html']

    if 'is_retweet' not in args:
        item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">' + parents + item['content_html'] + children + '</table>'
    item['content_html'] += '<div>&nbsp;</div>'
    return item


def get_tweet(tweet_result, tweet=None, user=None, is_thread=False, is_retweet=False):
    if tweet_result and tweet_result['__typename'] == 'TweetTombstone':
        item = {}
        body = tweet_result['tombstone']['text']['text']
        if tweet_result['tombstone']['text'].get('entities'):
            for it in tweet_result['tombstone']['text']['entities']:
                if it['ref']['type'] == 'TimelineUrl':
                    i = it['fromIndex']
                    j = it['toIndex']
                    body = body[:i] + '<a href="{}">'.format(it['ref']['url']) + body[i:j] + '</a>' + body[j:]
        if is_thread:
            item['content_html'] = '<tr><td colspan="2" style="padding:0 0 0 12px;"><table style="font-size:0.95em;">'
            item['content_html'] += '<tr><td style="width:12px; border-right:2px solid rgb(196, 207, 214);"></td><td style="width:12px;"></td><td><div>{}</div></td></tr>'.format(body)
            item['content_html'] += '</table></td></tr>'
        elif is_retweet:
            item['content_html'] = '<table style="font-size:0.95em; width:100%; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
            item['content_html'] += '<tr><td colspan="2"><div>{}</div></td></tr>'.format(body)
            item['content_html'] += '</table>'
        else:
            item['content_html'] = '<tr><td colspan="2"><div>{}</div></td></tr>'.format(body)
        return item

    if tweet_result and not tweet:
        tweet = tweet_result['legacy']
    if tweet_result and not user:
        user = tweet_result['core']['user_results']['result']['legacy']

    item = {}
    #item['id'] = tweet_result['rest_id']
    item['id'] = tweet['id_str']
    item['url'] = 'https://twitter.com/{}/status/{}'.format(user['screen_name'], item['id'])
    item['title'] = '@{} tweeted: {}'.format(user['screen_name'], tweet['full_text'])

    dt = dateutil.parser.parse(tweet['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = dt.astimezone(pytz.timezone(config.local_tz))
    date_str = '{}:{} {}&nbsp;&bull;&nbsp;{}. {}, {}'.format(int(dt_loc.strftime('%I')), dt_loc.strftime('%M'), dt_loc.strftime('%p').lower(), dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)

    item['author'] = {"name": user['name']}
    if user.get('verified'):
        checkmark = ' &#9989;'
    else:
        checkmark = ''

    if tweet.get('retweeted_status_result') and tweet['retweeted_status_result'].get('result'):
        rt_item = get_tweet(tweet['retweeted_status_result']['result'])
        if rt_item:
            item['content_html'] = '<tr><td colspan="2"><small>&#128257; <a href="https://twitter.com/{}">{}</a> Retweeted</small></td></tr>'.format(user['screen_name'], user['name']) + rt_item['content_html']
            return item

    note_tweet_entities = None
    if tweet_result and tweet_result.get('note_tweet'):
        body = tweet_result['note_tweet']['note_tweet_results']['result']['text']
        if tweet_result['note_tweet']['note_tweet_results']['result'].get('entity_set'):
            note_tweet_entities = tweet_result['note_tweet']['note_tweet_results']['result']['entity_set']
    else:
        body = tweet['full_text']

    body = body.replace('\n', '<br/>')
    item['tags'] = []
    if tweet['entities'].get('hashtags'):
        for it in tweet['entities']['hashtags']:
            body = re.sub(r'#{}\b'.format(it['text']), '<a href="https://twitter.com/hashtag/{0}">#{0}</a>'.format(it['text']), body, flags=re.I)
            item['tags'].append('#{}'.format(it['text']))
    elif note_tweet_entities and note_tweet_entities.get('hashtags'):
        for it in note_tweet_entities['hashtags']:
            body = re.sub(r'#{}\b'.format(it['text']), '<a href="https://twitter.com/hashtag/{0}">#{0}</a>'.format(it['text']), body, flags=re.I)
            item['tags'].append('#{}'.format(it['text']))

    if tweet['entities'].get('symbols'):
        for it in tweet['entities']['symbols']:
            body = re.sub(r'\${}\b'.format(it['text']), 'https://twitter.com/search?q=%24{0}&src=cashtag_click">${0}</a>'.format(it['text']), body, flags=re.I)
            item['tags'].append('${}'.format(it['text']))
    elif note_tweet_entities and note_tweet_entities.get('symbols'):
        for it in note_tweet_entities['symbols']:
            body = re.sub(r'\${}\b'.format(it['text']), 'https://twitter.com/search?q=%24{0}&src=cashtag_click">${0}</a>'.format(it['text']), body, flags=re.I)
            item['tags'].append('${}'.format(it['text']))

    if tweet['entities'].get('user_mentions'):
        for it in tweet['entities']['user_mentions']:
            body = re.sub(r'@{}\b'.format(it['screen_name']), '<a href="https://twitter.com/{0}">@{0}</a>'.format(it['screen_name']), body, flags=re.I)
            item['tags'].append('@{}'.format(it['screen_name']))
    elif note_tweet_entities and note_tweet_entities.get('user_mentions'):
        for it in note_tweet_entities['user_mentions']:
            body = re.sub(r'@{}\b'.format(it['screen_name']), '<a href="https://twitter.com/{0}">@{0}</a>'.format(it['screen_name']), body, flags=re.I)
            item['tags'].append('@{}'.format(it['screen_name']))

    if tweet['entities'].get('urls'):
        for it in tweet['entities']['urls']:
            if tweet_result and tweet_result.get('card'):
                if it['url'] == tweet_result['card']['rest_id']:
                    continue
            body = re.sub(r'\b{}\b'.format(it['url']), '<a href="{}">{}</a>'.format(it['expanded_url'], it['display_url']), body, flags=re.I)
    elif note_tweet_entities and note_tweet_entities.get('urls'):
        for it in note_tweet_entities['urls']:
            if tweet_result and tweet_result.get('card'):
                if it['url'] == tweet_result['card']['rest_id']:
                    continue
            body = re.sub(r'\b{}\b'.format(it['url']), '<a href="{}">{}</a>'.format(it['expanded_url'], it['display_url']), body, flags=re.I)

    if not item.get('tags'):
        del item['tags']

    if is_thread:
        item['content_html'] = '<tr><td colspan="2" style="padding:0 0 0 12px;"><table style="font-size:0.95em;">'
        avatar = '{}/image?url={}&height=24&mask=ellipse'.format(config.server, user['profile_image_url_https'])
        item['content_html'] += '<tr><td colspan="2"><img src="{}"/></td><td><a href="https://twitter.com/{}"><b>{}</b></a>{} <small>@{} &bull; <a href="{}">{}</a></small></td></tr>'.format(
            avatar, user['screen_name'], user['name'], checkmark, user['screen_name'], item['url'], date_str)
        item['content_html'] += '<tr><td style="width:12px; border-right:2px solid rgb(196, 207, 214);"></td><td style="width:12px;"></td><td><div>{}</div>'.format(body)
    elif is_retweet:
        item['content_html'] = '<table style="font-size:0.95em; width:100%; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
        avatar = '{}/image?url={}&height=24&mask=ellipse'.format(config.server, user['profile_image_url_https'])
        item['content_html'] += '<tr><td style="width:24px;"><img src="{}"/></td><td><a href="https://twitter.com/{}"><b>{}</b></a>{} <small>@{} &bull; <a href="{}">{}</a></small></td></tr>'.format(
            avatar, user['screen_name'], user['name'], checkmark, user['screen_name'], item['url'], date_str)
        item['content_html'] += '<tr><td colspan="2"><div>{}</div>'.format(body)
    else:
        item['content_html'] = ''
        avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, user['profile_image_url_https'])
        item['content_html'] += '<tr><td style="width:48px;"><img src="{}"/></td><td><a href="https://twitter.com/{}"><b>{}</b></a>{}<br/><small>@{}</small></td></tr>'.format(
            avatar, user['screen_name'], user['name'], checkmark, user['screen_name'])
        item['content_html'] += '<tr><td colspan="2"><div>{}</div>'.format(body)

    media_list = []
    if tweet.get('extended_entities') and tweet['extended_entities'].get('media'):
        media_list = tweet['extended_entities']['media'].copy()
    if tweet['entities'].get('media'):
        for media in tweet['entities']['media']:
            if not next((it for it in media_list if it['id_str'] == media['id_str']), None):
                media_list.append(media)
    if media_list:
        for media in media_list:
            item['content_html'] += '<div>&nbsp;</div>'
            if media['type'] == 'photo':
                item['content_html'] += utils.add_image(media['media_url_https'], img_style="width:100%; border-radius:10px;")
            elif media['type'] == 'video' or media['type'] == 'animated_gif':
                video = None
                if media['video_info'].get('variants'):
                    videos = []
                    for it in media['video_info']['variants']:
                        if it['content_type'] == 'video/mp4':
                            videos.append(it)
                    video = utils.closest_dict(videos, 'bitrate', 1000000)
                elif media.get('streams'):
                    video = media['streams'][0]
                if video:
                    item['content_html'] += utils.add_video(video['url'], video['content_type'], media['media_url_https'], img_style="width:100%; border-radius:10px;")
                else:
                    logger.warning('unhandled video media')
            else:
                logger.warning('unhandled media type ' + media['type'])
            item['content_html'] = item['content_html'].replace(media['url'], '')

    card = None
    if tweet_result and tweet_result.get('card'):
        card = tweet_result['card']['legacy']
    elif tweet.get('card'):
        card = tweet['card']
    if card:
        card_url = next((it for it in tweet['entities']['urls'] if it['url'] == card['url']), None)
        if card_url:
            if card_url.get('display_url'):
                item['content_html'] = item['content_html'].replace(card_url['url'], '<a href="{}">{}</a>'.format(card_url['expanded_url'], card_url['display_url']))
            else:
                item['content_html'] = item['content_html'].replace(card_url['url'], '')
            item['content_html'] += '<div>&nbsp;</div>' + get_card(card_url['expanded_url'], card)
        else:
            item['content_html'] += '<div>&nbsp;</div>' + get_card('', card)
            #logger.warning('unknown card url')

    if tweet.get('quoted_status_permalink'):
        if tweet_result and tweet_result.get('quoted_status_result'):
            rt_item = get_tweet(tweet_result['quoted_status_result']['result'], is_thread=False, is_retweet=True)
        else:
            #print(tweet['quoted_status_permalink']['expanded'])
            rt_item = get_content(tweet['quoted_status_permalink']['expanded'], {"is_retweet": True}, {"module": "twitter-v2"}, False)
        if rt_item:
            item['content_html'] += '<div>&nbsp;</div>' + rt_item['content_html']
            item['content_html'] = item['content_html'].replace(tweet['quoted_status_permalink']['url'], '')

    item['content_html'] += '</td></tr>'

    if is_thread:
        item['content_html'] += '</table></td></tr>'
    elif is_retweet:
        item['content_html'] += '</table>'
    else:
        item['content_html'] += '<tr><td colspan="2"><a href="{}"><small>{}</small></a></td></tr>'.format(item['url'], date_str)
    return item


def get_feed(url, args, site_json, save_debug=False):
    feed = None
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    query = parse_qs(split_url.query)
    if len(paths) == 1 and 'search' not in paths:
        # User tweets
        oauth1 = OAuth1(TW_CONSUMER_KEY, TW_CONSUMER_SECRET, config.twitter_oauth_token, config.twitter_oauth_token_secret, realm='https://api.twitter.com/', signature_type="AUTH_HEADER", signature_method="HMAC-SHA1")
        user_info = get_user_by_screen_name(paths[0], oauth1)
        if save_debug:
            utils.write_file(user_info, './debug/twitter.json')
        if user_info:
            tweets_json = get_user_tweets_and_replies(user_info['data']['user']['result']['rest_id'], oauth1)
            if tweets_json:
                if save_debug:
                    utils.write_file(tweets_json, './debug/feed.json')
                instruction = next((it for it in tweets_json['data']['user']['result']['timeline_v2']['timeline']['instructions'] if it['type'] == 'TimelineAddEntries'), None)
                if instruction:
                    n = 0
                    feed_items = []
                    for entry in instruction['entries']:
                        if entry['entryId'].startswith('tweet-'):
                            tweet_result = entry['content']['itemContent']['tweet_results']['result']
                            if save_debug:
                                logger.debug('getting content for ' + entry['entryId'])
                            item = get_tweet(tweet_result)
                            if item:
                                item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">' + item['content_html'] + '</table>'
                                if utils.filter_item(item, args) == True:
                                    feed_items.append(item)
                                    n += 1
                                    if 'max' in args:
                                        if n == int(args['max']):
                                            break
                    feed = utils.init_jsonfeed(args)
                    feed['title'] = '{} | Twitter'.format(user_info['data']['user']['result']['legacy']['screen_name'])
                    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    elif 'hashtag' in paths or 'search' in paths:
        # TODO
        return None
    return feed
