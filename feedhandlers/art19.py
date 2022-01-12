import feedparser, math, re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def calc_duration(sec):
  duration = []
  t = math.floor(float(sec) / 3600)
  if t >= 1:
    duration.append('{} hr'.format(t))
  t = math.ceil((float(sec) - 3600 * t) / 60)
  if t > 0:
    duration.append('{} min.'.format(t))
  return duration

def get_content(url, args, save_debug=False):
  show = ''
  m = re.search(r'\/shows\/([^\/]+)', url)
  if m:
    show = m.group(1)
  episode = ''
  m = re.search(r'\/episodes\/([^\/]+)', url)
  if m:
    episode = m.group(1)

  if episode:
    headers = {
      "Accept": "application/json",
      "Accept-Encoding": "gzip, deflate, br",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
      "Connection": "keep-alive",
      "Host": "rss.art19.com",
      "Origin": "https://art19.com",
      "Referer": "https://art19.com/",
      "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"96\", \"Microsoft Edge\";v=\"96\"",
      "sec-ch-ua-mobile": "?0",
      "sec-ch-ua-platform": "\"Windows\"",
      "Sec-Fetch-Dest": "empty",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Site": "same-origin",
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36 Edg/96.0.1054.43"
    }
    ep_json = utils.get_url_json('https://rss.art19.com/episodes/{}?content_only=true'.format(episode), headers=headers)
    if not ep_json:
      return None
    if save_debug:
      utils.write_file(ep_json, './debug/audio.json')

    item = {}
    item['id'] = ep_json['content']['episode_id']
    item['url'] = ep_json['content']['episode_share_url']
    item['title'] = ep_json['content']['episode_title']

    dt = datetime.fromisoformat(ep_json['performed_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = ep_json['content']['series_title']

    if ep_json['content']['artwork'].get('episode'):
      images = ep_json['content']['artwork']['episode']
    else:
      images = ep_json['content']['artwork']['show']
    img = utils.closest_dict(images, 'height', 640)
    item['_image'] = img['url']

    item['_audio'] = ep_json['content']['media']['mp3']['url']

    item['summary'] = ep_json['content']['episode_description']

    duration = calc_duration(ep_json['content']['duration'])
    poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a><br/>{}<br/>{}</small>'.format(item['url'], item['title'], ep_json['content']['series_show_page'], item['author']['name'], item['_display_date'], ', '.join(duration))
    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;">'.format(item['_audio'], poster, desc)
    if not 'embed' in args:
      item['content_html'] += '<blockquote><small>{}</small></blockquote>'.format(item['summary'])
    item['content_html'] += '</div>'
  else:
    try:
      d = feedparser.parse('https://rss.art19.com/' + show)
    except:
      logger.warning('Feedparser error https://rss.art19.com/' + show)
      return None

    item = {}
    item['id'] = d['feed']['link']
    item['url'] = d['feed']['link']
    item['title'] = d['feed']['title']

    ts = d['entries'][0]['published_parsed']
    dt = datetime(*ts[0:7]).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {"name": d['feed']['author']}

    if d['feed'].get('tags'):
      item['tags'] = []
      for tag in d['feed']['tags']:
        item['tags'].append(tag['term'])

    if d['feed'].get('image'):
      item['_image'] = d['feed']['image']['href']

    if d['feed'].get('summary'):
      item['summary'] = d['feed']['summary']

    poster = '{}/image?height=128&url={}'.format(config.server, quote_plus(item['_image']))
    desc = '<h3 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h3>by {}'.format(item['url'], item['title'], item['author']['name'])
    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"><br/><blockquote>'.format(item['url'], poster, desc)
    if 'max' in args:
      max = args['max'] - 1
    else:
      max = 2
    for i,entry in enumerate(d['entries']):
      episode = ''
      for link in entry['links']:
        m = re.search(r'\/episodes\/([a-f0-9\-]+)', link['href'])
        if m:
          episode = m.group(1)
          break
      t = entry['itunes_duration'].split(':')
      duration = calc_duration(int(t[0])*3600 + int(t[1])*60 + int(t[2]))
      poster = '{}/image?height=96&url={}&overlay=audio'.format(config.server, quote_plus(entry['image']['href']))
      ts = entry['published_parsed']
      dt = datetime(*ts[0:7]).replace(tzinfo=timezone.utc)
      display_date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
      desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}/episodes/{}">{}</a></h4><small>{}<br/>{}</small>'.format(item['url'], episode, entry['title'], display_date, ', '.join(duration))
      item['content_html'] += '<div><a href="https://rss.art19.com/episodes/{}.mp3"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"></div><br/>'.format(episode, poster, desc)
      if i == max:
        break
    if i == max:
      item['content_html'] += '<a href="{}">See more episodes...</a>'
    item['content_html'] += '</blockquote></div>'
  return item
