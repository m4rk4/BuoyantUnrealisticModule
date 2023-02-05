import html
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For now only handles embed comments
    # https://www.redditmedia.com/r/destiny2/comments/rbs51c/if_you_havent_seen_bungie_added_the_dance_to/?ref_source=embed&ref=share&embed=true
    split_url = urlsplit(url)
    #if 'redditmedia.com' not in split_url.netloc and 'embed=true' not in split_url.query:
    #    return None

    reddit_url = 'https://www.reddit.com{}.json'.format(split_url.path)
    reddit_json = utils.get_url_json(reddit_url)
    if not reddit_json:
        return None

    post_json = reddit_json[0]['data']['children'][0]['data']
    if save_debug:
        utils.write_file(post_json, './debug/reddit.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = 'https://www.reddit.com' + post_json['permalink']
    item['title'] = post_json['title']

    dt = datetime.fromtimestamp(post_json['created_utc']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = post_json['author']

    item['tags'] = []
    item['tags'].append(post_json['subreddit'])

    subreddit_json = utils.get_url_json('https://www.reddit.com/r/{}/about.json'.format(post_json['subreddit']))

    if subreddit_json['data'].get('community_icon'):
        img_src = subreddit_json['data']['community_icon'].replace('&amp;', '&')
    elif subreddit_json['data'].get('icon_img'):
        img_src = subreddit_json['data']['icon_img'].replace('&amp;', '&')
    else:
        img_src = 'https://www.redditinc.com/assets/images/site/reddit-logo.png'
    avatar = '{}/image?url={}&height=48&mask=circle'.format(config.server, quote_plus(img_src))

    item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{0}"/><a href="https://www.reddit.com/r/{1}"><b>r/{1}</b></a>&nbsp;&bull;&nbsp;Posted by u/{2}<br/><small>{3}</small></div><div style="clear:left;"></div>'.format(avatar, post_json['subreddit'], post_json['author'], utils.format_display_date(dt, False))

    item['content_html'] += '<p>{}</p>'.format(post_json['title'])

    if post_json.get('is_self') and post_json.get('selftext_html'):
        item['content_html'] += html.unescape(post_json['selftext_html'])

    elif post_json.get('is_video'):
        if post_json['domain'] == 'v.redd.it':
            item['_video'] = post_json['url_overridden_by_dest'] + '/DASH_480.mp4'
        else:
            item['_video'] = post_json['secure_media']['reddit_video']['fallback_url']
        if '.mp4' in item['_video']:
            video_type = 'video/mp4'
        elif '.m3u8' in item['_video']:
            video_type = 'application/x-mpegURL'
        poster = utils.closest_dict(post_json['preview']['images'][0]['resolutions'], 'width', 640)
        item['_image'] = poster['url'].replace('&amp;', '&')
        item['content_html'] += utils.add_video(item['_video'], video_type, item['_image'], width=480)

    elif post_json.get('secure_media'):
        embed_html = utils.add_embed(post_json['url_overridden_by_dest'])
        item['content_html'] += embed_html.replace('width:100%;', 'width:480px;')
        if post_json['secure_media']['oembed'].get('thumbnail_url'):
            item['_image'] = post_json['secure_media']['oembed']['thumbnail_url']

    elif post_json.get('gallery_data'):
        for it in post_json['gallery_data']['items']:
            media = post_json['media_metadata'][it['media_id']]
            if media['e'] == 'Image':
                img = utils.closest_dict(media['p'], 'x', 480)
                img_src = img['u'].replace('&amp;', '&')
                item['content_html'] += utils.add_image(img_src, width='480px')
                if not item.get('_image'):
                    item['_image'] = img_src
            else:
                logger.warning('unhandled media type {} in {}'.format(media['e'], url))

    elif post_json['domain'] == 'i.redd.it':
        item['_image'] = post_json['url_overridden_by_dest']
        item['content_html'] += utils.add_image(item['_image'], width='480px', link=item['_image'])

    elif post_json.get('preview') and post_json['preview'].get('images'):
        if 'reddit' not in post_json['domain']:
            link = post_json['url_overridden_by_dest']
            caption = '<a href="{}">{}</a>'.format(link, urlsplit(link).netloc)
        else:
            link = ''
            caption = ''
        for image in post_json['preview']['images']:
            img = utils.closest_dict(image['resolutions'], 'width', 480)
            img_src = img['url'].replace('&amp;', '&')
            item['content_html'] += utils.add_image(img_src, caption, width='480px', link=link)
            if not item.get('_image'):
                item['_image'] = img_src

    elif not post_json.get('is_self') and 'reddit' not in post_json['domain']:
        link = post_json['url_overridden_by_dest']
        caption = '<a href="{}">{}</a><br/>'.format(link, urlsplit(link).netloc)
        item['content_html'] += caption

    item['content_html'] += '<br/><a href="{}"><small>Open in Reddit</small></a></div>'.format(item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    # Top subreddits via https://subredditstats.com/
    feeds = ['https://www.reddit.com/r/funny/.rss',
             'https://www.reddit.com/r/AskReddit/.rss',
             'https://www.reddit.com/r/gaming/.rss',
             'https://www.reddit.com/r/aww/.rss',
             'https://www.reddit.com/r/Music/.rss',
             'https://www.reddit.com/r/pics/.rss',
             'https://www.reddit.com/r/worldnews/.rss',
             'https://www.reddit.com/r/movies/.rss',
             'https://www.reddit.com/r/science/.rss',
             'https://www.reddit.com/r/todayilearned/.rss',
             'https://www.reddit.com/r/videos/.rss',
             'https://www.reddit.com/r/news/.rss']
    for url in feeds:
        get_feed({"url": url}, True)
