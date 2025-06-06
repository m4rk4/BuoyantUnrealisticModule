import html, json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For now only handles embed comments
    # https://www.redditmedia.com/r/destiny2/comments/rbs51c/if_you_havent_seen_bungie_added_the_dance_to/?ref_source=embed&ref=share&embed=true
    split_url = urlsplit(url)
    if split_url.netloc == 'publish.reddit.com':
        # https://publish.reddit.com/embed?url=https://www.reddit.com/r/interestingasfuck/comments/1eahdat/unusually_large_eruption_just_happened_at/
        params = parse_qs(split_url.query)
        if 'url' in params:
            split_url = urlsplit(params['url'][0])

    #if 'redditmedia.com' not in split_url.netloc and 'embed=true' not in split_url.query:
    #    return None

    # ?sort=confidence or ?sort=top
    reddit_url = 'https://www.reddit.com{}.json?sort=top'.format(split_url.path)
    reddit_json = utils.get_url_json(reddit_url)
    if not reddit_json:
        return None
    if save_debug:
        utils.write_file(reddit_json, './debug/reddit.json')

    post_json = reddit_json[0]['data']['children'][0]['data']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

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
        img_src = 'https://redditinc.com/hubfs/Reddit%20Logos/Reddit_Favicon_FullColor_64x64-1.png'
    avatar = '{}/image?url={}&height=48&mask=circle'.format(config.server, quote_plus(img_src))

    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border-collapse:collapse; border-style:hidden; border-radius:10px; box-shadow:0 0 0 1px light-dark(#ccc, #333);">'

    item['content_html'] += '<tr><td style="width:48px; padding:8px;"><img src="{0}"/></td><td style="text-align:left; vertical-align:middle;"><a href="https://www.reddit.com/r/{1}"><b>r/{1}</b></a><br/><small>Posted by u/{2}</small></td><td style="width:32px; padding:0 8px 0 8px; text-align:right; vertical-align:middle;"><a href="{3}"><img src="https://redditinc.com/hubfs/Reddit%20Logos/Reddit_Favicon_FullColor_64x64-1.png" style="width:100%;"/></a></td></tr>'.format(avatar, post_json['subreddit'], post_json['author'], item['url'])

    # item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{0}"/><a href="https://www.reddit.com/r/{1}"><b>r/{1}</b></a>&nbsp;&bull;&nbsp;Posted by u/{2}<br/><small>{3}</small></div><div style="clear:left;"></div>'.format(avatar, post_json['subreddit'], post_json['author'], utils.format_display_date(dt, date_only=True))

    item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><strong>{}</strong></td></tr>'.format(post_json['title'])

    if post_json.get('selftext_html'):
        content_html = html.unescape(post_json['selftext_html'])
        if post_json.get('media_metadata'):
            soup = BeautifulSoup(content_html, 'html.parser')
            for el in soup.find_all(text=lambda text: isinstance(text, Comment)):
                el.extract()
            for media in post_json['media_metadata'].values():
                if media['e'] == 'Image':
                    el = soup.find('a', attrs={"href": re.compile(media['id'])})
                    if el:
                        img = utils.closest_dict(media['p'], 'x', 640)
                        img_src = img['u'].replace('&amp;', '&')
                        new_el = BeautifulSoup(utils.add_image(img_src, width='480px', link=media['s']['u']), 'html.parser')
                        if el.parent and el.parent.name == 'p':
                            el.parent.replace_with(new_el)
                        else:
                            el.replace_with(new_el)
                    else:
                        logger.warning('unable to find link for media id {} in {}'.format(media['id'], url))
                else:
                    logger.warning('unhandled media type {} in {}'.format(media['e'], url))
            content_html = str(soup)
        item['content_html'] += '<tr><td colspan="3" style="padding:8px;">' + content_html + '</td></tr>'

    if post_json.get('is_video'):
        video_src = config.server + '/videojs?src='
        if post_json['secure_media']['reddit_video'].get('hls_url'):
            video_src += quote_plus(post_json['secure_media']['reddit_video']['hls_url'])
            video_src += '&type=application%2Fx-mpegURL'
        elif post_json['secure_media']['reddit_video'].get('fallback_url'):
            video_src += quote_plus(post_json['secure_media']['reddit_video']['fallback_url'])
            video_src += '&type=video%2Fmp4'
        item['_image'] = post_json['preview']['images'][0]['source']['url'].replace('&amp;', '&')
        poster = '{}/image?url={}'.format(config.server, quote_plus(item['_image']))
        if post_json['secure_media']['reddit_video']['height'] > post_json['secure_media']['reddit_video']['width']:
            poster += '&letterbox=%28640%2C640%29&color=%23444'
        poster += '&overlay=video'
        video_src += '&poster=' + quote_plus(item['_image'])
        item['content_html'] += '<tr><td colspan="3" style="padding:0;"><div style="padding:8px;"><a href="{}" target="_blank"><img src="{}" style="display:block; width:100%;" /></a></div></td></tr>'.format(video_src, poster)

    elif post_json.get('secure_media'):
        embed_html = utils.add_embed(post_json['url_overridden_by_dest'])
        item['content_html'] += embed_html.replace('width:100%;', 'width:480px;')
        if post_json['secure_media']['oembed'].get('thumbnail_url'):
            item['_image'] = post_json['secure_media']['oembed']['thumbnail_url']

    elif post_json.get('gallery_data'):
        gallery_images = []
        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for it in post_json['gallery_data']['items']:
            media = post_json['media_metadata'][it['media_id']]
            if media['e'] == 'Image':
                img_src = media['s']['u'].replace('&amp;', '&')
                if not item.get('_image'):
                    item['_image'] = img_src
                img = utils.closest_dict(media['p'], 'x', 640)
                thumb = img['u'].replace('&amp;', '&')
                gallery_html += '<div style="flex:1; min-width:200px;"><a href="{0}" target="_blank"><img src="{0}" style="display:block; width:100%;" /></a></div>'.format(img_src, thumb)
                gallery_images.append({"src": img_src, "caption": "", "thumb": thumb})
                # item['content_html'] += '<tr><td colspan="3" style="padding:8px 0 8px 0;"><div><a href="{}"><img src="{}" style="display:block; width:100%;" /></a></div></td></tr>'.format(img_src, thumb)
            else:
                logger.warning('unhandled media type {} in {}'.format(media['e'], url))
        gallery_html += '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += '<tr><td colspan="3" style="padding:0;"><div style="padding:8px;"><a href="{}" target="_blank">View photo gallery</a></div>'.format(gallery_url)
        item['content_html'] += gallery_html + '</td></tr>'

    elif post_json['domain'] == 'i.redd.it':
        item['_image'] = post_json['url_overridden_by_dest']
        item['content_html'] += '<tr><td colspan="3" style="padding:0;"><div><a href="{0}" target="_blank"><img src="{0}" style="display:block; width:100%;" /></a></div></td></tr>'.format(item['_image'])

    elif 'reddit' not in post_json['domain'] and not post_json['domain'].startswith('self.'):
        # embed_item = utils.get_content(post_json['url_overridden_by_dest'], {"embed": True}, False)
        embed_html = utils.add_embed(post_json['url_overridden_by_dest'])
        if not embed_html.startswith('<blockquote><b>Embedded content from'):
            item['content_html'] += '<tr><td colspan="3" style="padding:8px;">' + embed_html + '</td></tr>'
        elif post_json.get('preview') and post_json['preview'].get('images'):
            logger.warning('TODO: preview')
        else:
            item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><a href="{}" target="_blank">{}</a>&nbsp;🡵</td></tr>'.format(post_json['url_overridden_by_dest'], urlsplit(post_json['url_overridden_by_dest']).netloc)

    item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><small>🡅 {} &bull; 🗩 {}</small></td></tr>'.format(post_json['ups'], post_json['num_comments'])

    item['content_html'] += '<tr><td colspan="3" style="padding:8px;"><a href="{}"><small>{}</small></a></td></tr>'.format(item['url'], item['_display_date'])

    item['content_html'] += '</table>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
