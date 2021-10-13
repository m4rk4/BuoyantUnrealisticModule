import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

def replace_entity(matchobj):
  if matchobj.group(1) == '@':
    return '<a href="https://www.tiktok.com/@{0}">@{0}</a>'.format(matchobj.group(2))
  elif matchobj.group(1) == '#':
    return '<a href="https://www.tiktok.com/tag/{0}">#{0}</a>'.format(matchobj.group(2))
  return matchobj.group(0)

def get_item(content, args, save_debug=False):
  item = {}

  if content.get('itemInfos'):
    item['id'] = content['itemInfos']['id']
    item['url'] = 'https://www.tiktok.com/@{}/video/{}'.format(content['authorInfos']['uniqueId'], content['itemInfos']['id'])
    item['title'] = content['itemInfos']['text']

    dt = datetime.fromtimestamp(int(content['itemInfos']['createTime']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = '{} (@{})'.format(content['authorInfos']['nickName'], content['authorInfos']['uniqueId'])
    avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(content['authorInfos']['covers'][0]))
    author_info = '<a href="https://www.tiktok.com/@{0}"><b>{0}</b></a>&nbsp;<small>{1}</small>'.format(content['authorInfos']['uniqueId'], content['authorInfos']['nickName'])

    if content.get('textExtra'):
      item['tags'] = []
      for tag in content['textExtra']:
        item['tags'].append(tag['HashtagName'])

    item['_image'] = content['itemInfos']['coversOrigin'][0]
    item['_video'] = content['itemInfos']['video']['urls'][0]

    music_info = '<a href="https://www.tiktok.com/music/{}-{}?lang=en">{} &ndash; {}</a>'.format(content['musicInfos']['musicName'].replace(' ', '-'), content['musicInfos']['musicId'], content['musicInfos']['musicName'], content['musicInfos']['authorName'])

    item['summary'] = re.sub(r'(@|#)(\w+)', replace_entity, content['itemInfos']['text'], flags=re.I)
  else:
    item['id'] = content['id']
    item['url'] = 'https://www.tiktok.com/@{}/video/{}'.format(content['author']['uniqueId'], content['id'])
    item['title'] = content['desc']

    dt = datetime.fromtimestamp(int(content['createTime']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = '{} (@{})'.format(content['author']['nickname'], content['author']['uniqueId'])
    avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(content['author']['avatarThumb']))
    author_info = '<a href="https://www.tiktok.com/@{0}"><b>{0}</b></a>&nbsp;<small>{1}</small>'.format(content['author']['uniqueId'], content['author']['nickname'])

    if content.get('textExtra'):
      item['tags'] = []
      for tag in content['textExtra']:
        item['tags'].append(tag['hashtagName'])

    item['_image'] = content['video']['originCover']
    item['_video'] = content['video']['playAddr']
    item['_audio'] = content['music']['playUrl']
    music_info = '<a href="{}">{} &ndash; {}</a>'.format(item['_audio'], content['music']['title'], content['music']['authorName'])

    item['summary'] = re.sub(r'(@|#)(\w+)', replace_entity, content['desc'], flags=re.I)

  item['content_html'] = '<table style="width:500px !important; margin-left:auto; margin-right:auto; padding:10px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td style="width:50px;"><img style="vertical-align: middle;" src="{}" /></td><td>{}</td></tr>'.format(avatar, author_info)
  item['content_html'] += '<tr><td>&nbsp;</td><td>{}</td></tr>'.format(item['summary'])

  if music_info:
    music_svg = '<svg width="18" height="18" viewBox="0 0 48 48" fill="currentColor" xmlns="http://www.w3.org/2000/svg" style="transform: translateY(4px);"><path fill-rule="evenodd" clip-rule="evenodd" d="M35.0001 10.7587C35.0001 10.1169 34.4041 9.64129 33.7784 9.78359L17.7902 13.4192C17.335 13.5227 17.0119 13.9275 17.0119 14.3943V37.9972H17.0109C17.0374 40.1644 14.8022 42.4189 11.612 43.2737C8.05093 44.2279 4.64847 43.0769 4.01236 40.7028C3.37624 38.3288 5.74735 35.6308 9.30838 34.6766C10.606 34.3289 11.8826 34.2608 13.0119 34.4294V14.3943C13.0119 12.0601 14.6271 10.0364 16.9033 9.5188L32.8914 5.88317C36.0204 5.17165 39.0001 7.54986 39.0001 10.7587V33.1191C39.084 35.3108 36.8331 37.6109 33.6032 38.4763C30.0421 39.4305 26.6397 38.2795 26.0036 35.9055C25.3675 33.5315 27.7386 30.8334 31.2996 29.8792C32.5961 29.5319 33.8715 29.4635 35.0001 29.6316V10.7587Z"></path></svg>'
    item['content_html'] += '<tr><td>&nbsp;</td><td>{}&nbsp;{}</td></tr>'.format(music_svg, music_info)

  item['content_html'] += '<tr><td>&nbsp;</td><td>{}</td></tr></table>'.format(utils.add_video(item['_video'], 'video/mp4', item['_image'], img_style='border-radius:10px;', fig_style=' margin:0; padding:0;'))
  return item

def get_content(url, args, save_debug=False):
  if url.startswith('https'):
    page_url = utils.clean_url(url)
  else:
    # url is the video id
    page_url = 'https://www.tiktok.com/embed/v2/{}?lang=en-US'.format(url)

  page_html = utils.get_url_html(page_url)
  if not page_html:
    return None

  soup = BeautifulSoup(page_html, 'html.parser')
  next_data = soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    return None

  next_json = json.loads(next_data.string)
  if save_debug:
    utils.write_file(next_json, './debug/tiktok.json')

  if '/embed/' in url:
    return get_item(next_json['props']['pageProps']['videoData'], args, save_debug)

  return get_item(next_json['props']['pageProps']['itemInfo']['itemStruct'], args, save_debug)

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
