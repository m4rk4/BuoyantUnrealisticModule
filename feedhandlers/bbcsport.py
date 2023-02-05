import json, re
from datetime import datetime

import utils
from feedhandlers import bbc

import logging
logger = logging.getLogger(__name__)

def format_event(event_json):
  # Only for is for Soccer (Football)
  content_html = ''
  if event_json['eventKey'].startswith('EFBO'):
    content_html += '<table style="width:100%; margin-left:auto; margin-right:auto; table-layout:fixed;">'
    content_html += '<tr><th style="text-align:right; padding-right:8px;">{}</th><th style="text-align:left; padding-left:8px;">{}</th></tr>'.format(event_json['formattedDateInUKTimeZone']['dateString'], event_json['competitionNameString'])
    content_html += '<tr><td style="text-align:right; vertical-align:middle; font-size:1.5em;">{}<div style="display:inline-block; width:1.2em; line-height:1.2em; text-align:center; background-color:#ffd230;">{}</div></td>'.format(event_json['homeTeam']['name']['full'], event_json['homeTeam']['scores']['score'])
    content_html += '<td style="text-align:left; vertical-align:middle; font-size:1.5em;"><div style="display:inline-block; width:1.2em; line-height:1.2em; text-align:center; background-color:#ffd230;">{}</div>{}</td></tr>'.format(
      event_json['awayTeam']['scores']['score'], event_json['awayTeam']['name']['full'])
    for i in range(max(len(event_json['homeTeam']['playerActions']), len(event_json['awayTeam']['playerActions']))):
      try:
        player_action = event_json['homeTeam']['playerActions'][i]['name']['abbreviation'] + '('
        for action in event_json['homeTeam']['playerActions'][i]['actions']:
          if action['type'] == 'goal':
            player_action += '&#x26BD;'
          elif action['type'] == 'yellow-card':
            player_action += '<span style="color:yellow;">&#x25AE;</span>'
          elif action['type'] == 'red-card':
            player_action += '<span style="color:red;">&#x25AE;</span>'
          elif action['type'] == 'yellow-red-card':
            player_action += '<span style="color:yellow;">&#x25AE;</span><span style="color:red;">&#x25AE;</span>'
          player_action += action['displayTime']
          player_action += ', '
        player_action = player_action[:-2] + ')'
      except IndexError:
        player_action = ''
      content_html += '<tr><td style="font-size:0.8em; line-height:1.1em; text-align:right; padding-right:0.5em; vertical-align:middle;">{}</td>'.format(player_action)
      try:
        player_action = event_json['awayTeam']['playerActions'][i]['name']['abbreviation'] + '('
        for action in event_json['awayTeam']['playerActions'][i]['actions']:
          if action['type'] == 'goal':
            player_action += '&#x26BD;'
          elif action['type'] == 'yellow-card':
            player_action += '<span style="color:yellow;">&#x25AE;</span>'
          elif action['type'] == 'red-card':
            player_action += '<span style="color:red;">&#x25AE;</span>'
          elif action['type'] == 'yellow-red-card':
            player_action += '<span style="color:yellow;">&#x25AE;</span><span style="color:red;">&#x25AE;</span>'
          player_action += action['displayTime']
          player_action += ', '
        player_action = player_action[:-2] + ')'
      except IndexError:
        player_action = ''
      content_html += '<td style="font-size:0.8em; line-height:1.1em; text-align:left; padding-left:0.5em; vertical-align:middle;">{}</td></tr>'.format(player_action)
    content_html += '</table><br/>'
  return content_html

def format_content(block, table=False):
  content_html = ''
  tag = ''
  extra_attr = ''

  if block['name'] == 'text':
    content_html += block['text']

  elif block['name'] == 'paragraph':
    if table:
      tag = 'span'
    else:
      tag = 'p'

  elif block['name'] == 'bold':
    tag = 'b'

  elif block['name'] == 'italic':
    tag = 'i'

  elif block['name'] == 'crosshead':
    tag = 'h3'

  elif block['name'] == 'link':
    url = ''
    caption = ''
    for child in block['children']:
      if child['name'] == 'caption':
        caption = format_content(child)
      elif child['name'] == 'url':
        url = format_content(child)
    content_html += '<a href="{}">{}</a>'.format(url, caption)

  elif block['name'] == 'caption':
    for child in block['children']:
      content_html += format_content(child)

  elif block['name'] == 'url':
    for attr in block['attributes']:
      if attr['name'] == 'href':
        content_html += attr['value']

  elif block['name'] == 'list':
    for attr in block['attributes']:
      if attr['name'] == 'type':
        if attr['value'] == 'unordered':
          tag = 'ul'
        elif attr['value'] == 'ordered':
          tag = 'ol'
    if not tag:
      logger.warning('unknown list type')
      tag = 'ul'

  elif block['name'] == 'listItem':
    tag = 'li'

  elif block['name'] == 'table':
    table = True
    tag = 'table'
    extra_attr = ' style="min-width:80%; margin-left:auto; margin-right:auto; border:1px solid black; border-collapse:collapse;"'

  elif block['name'] == 'row':
    tag = 'tr'

  elif block['name'] == 'header':
    tag = 'th'

  elif block['name'] == 'cell':
    tag = 'td'

  elif block['name'] == 'image':
    if block['imageData'].get('iChefHref'):
      img_src = block['imageData']['iChefHref'].replace('{width}', '976')
    else:
      img_src = block['imageData']['href']
    captions = []
    if block['imageData'].get('caption'):
      captions.append(block['imageData']['caption'])
    if block['imageData'].get('copyrightHolder'):
      captions.append(block['imageData']['copyrightHolder'])
    content_html += utils.add_image(img_src, ' | '.join(captions))

  elif block['name'] == 'video':
    video_src, caption = bbc.get_video_src(block['videoData']['vpid'])
    if block['videoData'].get('iChefHref'):
      poster = block['videoData']['iChefHref'].replace('{width}', '976')
    else:
      poster = block['videoData']['image'].replace('$recipe', '976x549')
    if video_src:
      if block['videoData'].get('caption'):
        caption = block['videoData']['caption']
      content_html += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
    else:
      content_html += utils.add_image(poster, caption)

  elif block['name'] == 'embed':
    href = ''
    for child in block['children']:
      if child['name'] == 'href':
        href = child['children'][0]['text']
    content_html += utils.add_embed(href)

  elif block['name'] == 'comment' or block['name'] == 'pullOut':
    pass

  else:
    logger.warning('unhandled block name ' + block['name'])

  if tag:
    content_html += '<' + tag
    for attr in block['attributes']:
      content_html += ' {}="{}"'.format(attr['name'], attr['value'])
    content_html += extra_attr + '>'
    for child in block['children']:
      content_html += format_content(child, table)
    content_html += '</{}>'.format(tag)

  return content_html

def get_content(url, args, site_json, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  article_json = None
  event_json = None
  for m in re.findall(r'<script>Morph\.toInit\.payloads\.push\(function\(\) { Morph\.setPayload\(\'([^\']+)\', ({.+?})\); }\);<\/script>', article_html):
    payload_json = json.loads(m[1])
    try:
      if payload_json['body']['content']['article'].get('assetId'):
        article_json = payload_json['body']['content']['article']
    except:
      pass
    try:
      if payload_json['body']['event'].get('eventKey'):
        event_json = payload_json['body']['event']
    except:
      pass

  if not article_json:
    logger.warning('unable to find article data in ' + url)
    return None

  body_json = json.loads(article_json['body'])
  article_json['body'] = body_json
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  item = {}
  item['id'] = article_json['assetId']
  item['url'] = url
  item['title'] = article_json['headline']

  dt = datetime.fromisoformat(article_json['dateTimeInfo']['dateTime'])
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)

  item['author'] = {}
  if article_json.get('contributor'):
    item['author']['name'] = re.sub('^By ', '', article_json['contributor']['name'])
  else:
    item['author']['name'] = 'BBC Sport'

  if article_json.get('section'):
    item['tags'] = [article_json['section']['name']]

  if body_json[0]['name'] == 'image':
    item['_image'] = body_json[0]['imageData']['iChefHref'].replace('{width}', '976')

  item['content_html'] = ''
  if event_json:
    if save_debug:
      utils.write_file(event_json, './debug/event.json')
    item['content_html'] += format_event(event_json)

  for block in body_json:
    item['content_html'] += format_content(block)
  return item
