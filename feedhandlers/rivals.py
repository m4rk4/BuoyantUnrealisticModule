import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import config, utils
from feedhandlers import brightcove

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://n.rivals.com/api/v2/content/contents/' + paths[-1]
    content_json = utils.get_url_json(api_url)
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['permalink']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['published_time']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['modified_time']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": content_json['author_info']['publisher_name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    item['tags'].append(content_json['sport'])
    item['tags'].append(content_json['publishing_site']['name'])
    item['tags'].append(content_json['publishing_site']['friendly_name'])
    item['tags'].append(content_json['publishing_site']['nickname'])

    item['image'] = content_json['image_url']

    item['summary'] = content_json['summary']

    item['content_html'] = ''
    for block in content_json['body']:
        if block['type'] == 'text':
            item['content_html'] += block['data']['text']
        elif block['type'] == 'heading':
            item['content_html'] += '<h2>' + block['data']['text'] + '</h3>'
        elif block['type'] == 'divider':
            item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        elif block['type'] == 'image':
            item['content_html'] += utils.add_image(block['data']['large_url'].replace('t_large', 'w_1000'), block['data']['caption'])
        elif block['type'] == 'video' and block['data']['source'] == 'brightcove':
            yql_url = 'https://video-api.yql.yahoo.com/v1/video/sapi/streams/{}?srid=&protocol=http&format=m3u8%2Cmp4%2Cwebm&rt=html&devtype=desktop&offnetwork=false&plid=&region=US&site=rivals&expb=&expn=&bckt=Treatment_Oath_Player&lang=en-US&width=1280&height=720&resize=true&ps=&autoplay=true&image_sizes=&excludePS=true&isDockable=0&acctid=&synd=&pspid=&plidl=&topic=&pver=&try=1&failover_count=0&ads=ima&ad.pl=up&ad.pd=&ad.pt=&ad.pct=&evp=bcp&hlspre=false&ad.plseq=1&gdpr=false&iabconsent=&usprv=&gpp=&gppSid=-1'.format(block['data']['remote_id'])
            yql_json = utils.get_url_json(yql_url)
            if yql_json and len(yql_json['query']['results']['mediaObj']) > 0:
                video = yql_json['query']['results']['mediaObj'][0]
                stream = video['streams'][0]
                item['content_html'] += utils.add_video(stream['host'] + stream['path'], stream['mime_type'], video['meta']['thumbnail'], video['meta']['title'])
        elif block['type'] == 'prospectcard':
            api_json = utils.get_url_json('https://n.rivals.com/api/v2/prospects/prospect/' + str(block['data']['id']))
            if api_json:
                prospect = api_json['prospect']
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; width:90%; margin:auto; padding:8px; border:1px solid #444; border-radius:10px;">'
                if prospect.get('profile_image_url'):
                    item['content_html'] += '<div style="flex:1; max-width:200px;"><a href="{}"><img src="{}" style="width:200px; height:200px; object-fit:cover; object-position:0 0;"></a></div>'.format(prospect['athlete_url'], prospect['profile_image_url'])
                else:
                    item['content_html'] += '<div style="flex:1; max-width:200px;"><a href="{}"><img src="https://n.rivals.com/static/icons/icons_prospectprofile_avatar.svg" style="width:200px; height:200px; object-fit:cover; object-position:0 0;"></a></div>'.format(prospect['athlete_url'])

                item['content_html'] += '<div style="flex:1; min-width:160px;">'
                item['content_html'] += '<div style="font-size:1.05em; font-weight:bold;">{}</div>'.format(prospect['full_name'])
                f, i = divmod(prospect['height'] / 12, 1)
                item['content_html'] += '<div style="font-size:0.8em; margin-top:0.5em;">{:.0f}\'{:.0f}" | {:.0f} lbs | {}</div>'.format(f, i*12, prospect['weight'], prospect['position_abbreviation'])
                item['content_html'] += '<div style="font-size:0.8em; margin-top:0.5em;">{}<br/>{}</div>'.format(prospect['highschool_name'], prospect['hometown'])
                item['content_html'] += '<div style="font-size:0.8em; margin-top:0.5em;">Class of {}</div>'.format(prospect['recruit_year'])
                item['content_html'] += '</div>'

                item['content_html'] += '<div style="flex:1; min-width:160px; text-align:center;">'
                item['content_html'] += utils.add_stars(prospect['stars'], 5, star_size='2em', center=False)
                if prospect['rivals_rating'] == 0:
                    rank = 'N/A'
                else:
                    rank = prospect['rivals_rating']
                item['content_html'] += '<div style="display:flex; align-items:center; justify-content:center; margin:0.5em 0 0.5em 0;"><div style="font-size:1.6em; font-weight:bold;">{}</div><div style="font-size:0.8em; padding:2px 0px 2px 4px;"><b>Rivals</b><br/>Rating</div></div>'.format(rank)
                if prospect['status'] == 'undecided':
                    item['content_html'] += '<div><b>undecided</b></div>'
                else:
                    item['content_html'] += '<div style="display:flex;"><div><img src="{}" style="width:2.5em; height:2.5em;"></div><div style="font-size:0.8em; padding:2px 0px 2px 4px;"><b>{}</b><br/>{}</div></div>'.format(prospect['committed_college_logo'], prospect['status'], prospect['commit_date'])
                item['content_html'] += '</div>'

                item['content_html'] += '<div style="flex:1; max-width:100px;">'

                item['content_html'] += '<div style="display:flex;">'
                if prospect['national_rank_change'] > 0:
                    item['content_html'] += '<div style="color:green; padding-top:0.5em; width:1em;">▲</div>'
                elif prospect['national_rank_change'] < 0:
                    item['content_html'] += '<div style="color:red; padding-top:0.5em; width:1em;">▼</div>'
                else:
                    item['content_html'] += '<div style="padding-top:0.5em; width:1em;"></div>'
                if prospect['national_rank']:
                    rank = prospect['national_rank']
                else:
                    rank = '&ndash;'
                item['content_html'] += '<div style="font-size:0.8em; text-align:center; min-width:3em;"><span style="font-size:2em; font-weight:bold;">{}</span><br/>NATL</div>'.format(rank)
                item['content_html'] += '</div>'

                item['content_html'] += '<div style="display:flex;">'
                if prospect['state_rank_change'] > 0:
                    item['content_html'] += '<div style="color:green; padding-top:0.5em; width:1em;">▲</div>'
                elif prospect['state_rank_change'] < 0:
                    item['content_html'] += '<div style="color:red; padding-top:0.5em; width:1em;">▼</div>'
                else:
                    item['content_html'] += '<div style="padding-top:0.5em; width:1em;"></div>'
                if prospect['state_rank']:
                    rank = prospect['state_rank']
                else:
                    rank = '&ndash;'
                item['content_html'] += '<div style="font-size:0.8em; text-align:center; min-width:3em;"><span style="font-size:2em; font-weight:bold;">{}</span><br/>ST</div>'.format(rank)
                item['content_html'] += '</div>'

                item['content_html'] += '<div style="display:flex;">'
                if prospect['position_rank_change'] > 0:
                    item['content_html'] += '<div style="color:green; padding-top:0.5em; width:1em;">▲</div>'
                elif prospect['position_rank_change'] < 0:
                    item['content_html'] += '<div style="color:red; padding-top:0.5em; width:1em;">▼</div>'
                else:
                    item['content_html'] += '<div style="padding-top:0.5em; width:1em;"></div>'
                if prospect['position_rank']:
                    rank = prospect['position_rank']
                else:
                    rank = '&ndash;'
                item['content_html'] += '<div style="font-size:0.8em; text-align:center; min-width:3em;"><span style="font-size:2em; font-weight:bold;">{}</span><br/>POS</div>'.format(rank)
                item['content_html'] += '</div>'
                item['content_html'] += '</div>'
                item['content_html'] += '</div><div>&nbsp;</div>'
        elif block['type'] == 'ad':
            continue
        else:
            logger.warning('unhandled body block type {} in {}'.format(block['type'], item['url']))

    if content_json['is_premium']:
        item['content_html'] += '<div>&nbsp;</div><div style="text-align:center; font-size:1.1em; font-weight:bold;">Premium content requires a subscription</div>'
    return item