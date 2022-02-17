import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def replace_entity(matchobj):
  if matchobj.group(1) == '@':
    return '<a href="https://www.tiktok.com/@{0}">@{0}</a>'.format(matchobj.group(2))
  elif matchobj.group(1) == '#':
    return '<a href="https://www.tiktok.com/tag/{0}">#{0}</a>'.format(matchobj.group(2))
  return matchobj.group(0)

def get_content(url, args, save_debug=False):
  if url.startswith('https'):
    m = re.search(r'/video/(\d+)', url)
    if not m:
      logger.warning('unable to determine video id in ' + url)
      return None
    video_id = m.group(1)
  else:
    # url is the video id
    video_id = url

  page_html = utils.get_url_html('https://www.tiktok.com/embed/v2/{}?lang=en-US'.format(video_id))
  if not page_html:
    return None

  soup = BeautifulSoup(page_html, 'html.parser')
  next_data = soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    return None

  next_json = json.loads(next_data.string)
  if save_debug:
    utils.write_file(next_json, './debug/tiktok.json')

  video_data = next_json['props']['pageProps']['videoData']

  item = {}

  item['id'] = video_data['itemInfos']['id']
  item['url'] = 'https://www.tiktok.com/@{}/video/{}'.format(video_data['authorInfos']['uniqueId'], video_data['itemInfos']['id'])
  item['title'] = video_data['itemInfos']['text']

  dt = datetime.fromtimestamp(int(video_data['itemInfos']['createTime']))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = '{} (@{})'.format(video_data['authorInfos']['nickName'], video_data['authorInfos']['uniqueId'])
  avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(video_data['authorInfos']['covers'][0]))
  author_info = '<a href="https://www.tiktok.com/@{0}"><b>{0}</b></a>&nbsp;'.format(video_data['authorInfos']['uniqueId'])
  if video_data['authorInfos']['verified']:
    verified_svg = '<svg class="tiktok-shsbhf-StyledVerifyBadge e1aglo370" width="14" height="14" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="24" cy="24" r="24" fill="#20D5EC"></circle><path fill-rule="evenodd" clip-rule="evenodd" d="M37.1213 15.8787C38.2929 17.0503 38.2929 18.9497 37.1213 20.1213L23.6213 33.6213C22.4497 34.7929 20.5503 34.7929 19.3787 33.6213L10.8787 25.1213C9.70711 23.9497 9.70711 22.0503 10.8787 20.8787C12.0503 19.7071 13.9497 19.7071 15.1213 20.8787L21.5 27.2574L32.8787 15.8787C34.0503 14.7071 35.9497 14.7071 37.1213 15.8787Z" fill="white"></path></svg>'
    author_info += '{}&nbsp;'.format(verified_svg)
  author_info += '<small>{}</small>'.format(video_data['authorInfos']['nickName'])

  if video_data.get('textExtra'):
    item['tags'] = []
    for tag in video_data['textExtra']:
      item['tags'].append(tag['HashtagName'])

  item['_image'] = video_data['itemInfos']['coversOrigin'][0]
  item['_video'] = video_data['itemInfos']['video']['urls'][0]

  music_info = '<a href="https://www.tiktok.com/music/{}-{}?lang=en">{} &ndash; {}</a>'.format(video_data['musicInfos']['musicName'].replace(' ', '-'), video_data['musicInfos']['musicId'], video_data['musicInfos']['musicName'], video_data['musicInfos']['authorName'])

  item['summary'] = re.sub(r'(@|#)(\w+)', replace_entity, video_data['itemInfos']['text'], flags=re.I)

  item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div></div><p>{}</p>'.format(avatar, author_info, item['summary'])

  if music_info:
    music_svg = '<svg width="18" height="18" viewBox="0 0 48 48" fill="currentColor" xmlns="http://www.w3.org/2000/svg" style="transform: translateY(4px);"><path fill-rule="evenodd" clip-rule="evenodd" d="M35.0001 10.7587C35.0001 10.1169 34.4041 9.64129 33.7784 9.78359L17.7902 13.4192C17.335 13.5227 17.0119 13.9275 17.0119 14.3943V37.9972H17.0109C17.0374 40.1644 14.8022 42.4189 11.612 43.2737C8.05093 44.2279 4.64847 43.0769 4.01236 40.7028C3.37624 38.3288 5.74735 35.6308 9.30838 34.6766C10.606 34.3289 11.8826 34.2608 13.0119 34.4294V14.3943C13.0119 12.0601 14.6271 10.0364 16.9033 9.5188L32.8914 5.88317C36.0204 5.17165 39.0001 7.54986 39.0001 10.7587V33.1191C39.084 35.3108 36.8331 37.6109 33.6032 38.4763C30.0421 39.4305 26.6397 38.2795 26.0036 35.9055C25.3675 33.5315 27.7386 30.8334 31.2996 29.8792C32.5961 29.5319 33.8715 29.4635 35.0001 29.6316V10.7587Z"></path></svg>'
    item['content_html'] += '<p>{}&nbsp;{}</p>'.format(music_svg, music_info)

  #item['content_html'] += '<tr><td>&nbsp;</td><td>{}</td></tr></table>'.format(utils.add_video(item['_video'], 'video/mp4', item['_image'], fig_style=' margin:0; padding:0;'))

  item['content_html'] += utils.add_video(item['_video'], 'video/mp4', item['_image'], width=480, fig_style=' margin:0; padding:0;')
  item['content_html'] += '<br/><a href="{}"><small>Open in TikTok</small></a></div>'.format(item['url'])
  return item


def get_feed(args, save_debug=False):
  page_html = utils.get_url_html(args['url'])
  if not page_html:
    return None
  if False:
    utils.write_file(page_html, './debug/tiktok.html')

  page_soup = BeautifulSoup(page_html, 'html.parser')
  next_data = page_soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    return None

  next_json = json.loads(next_data.string)
  if save_debug:
    utils.write_file(next_json, './debug/tiktok.json')

  n = 0
  items = []
  for content in next_json['props']['pageProps']['items']:
    item = get_item(content, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed
