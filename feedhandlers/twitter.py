import json, re
from datetime import datetime
import snscrape.modules.twitter as sntwitter
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

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
        return '<a href="https://twitter.com/search?q=%24{0}&src=cashtag_click">${0}</a>'.format(matchobj.group(2))
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
          media_html += '<video style="width:100%; border-radius:10px;" controls poster="{0}"><source src="{1}" type="video/mp4"></video><a href="{1}"><small>Open video</small></a>'.format(tweet_json['video']['poster'], video['src'])
          break
    else:
      video_url = tweet_json['entities']['media'][0]['expanded_url']
      play_svg = '<div style="position:absolute; width:32px; height:32px; left:50%; top:50%; transform:translate(-50%,-50%); border:4px solid white; border-radius:9999px; background-color:rgb(29,161,242);"></div><div style="position:absolute; width:24px; height:24px; left:50%; top:50%; transform:translate(-50%,-50%);"><svg viewBox="0 0 24 24"><g><path stroke="white" fill="white" d="M20.436 11.37L5.904 2.116c-.23-.147-.523-.158-.762-.024-.24.132-.39.384-.39.657v18.5c0 .273.15.525.39.657.112.063.236.093.36.093.14 0 .28-.04.402-.117l14.53-9.248c.218-.138.35-.376.35-.633 0-.256-.132-.495-.348-.633z"></path></g></svg></div>'
      media_html += '<div style="position:relative"><img width="100%" style="border-radius:10px" src="{}" /><a href="{}">{}</a></div><a href="{}"><small>View video on Twitter</small></a>'.format(tweet_json['video']['poster'], video_url, play_svg, video_url)

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

  link_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" style="width:0.9em; height:0.9em;"><g><path d="M11.96 14.945c-.067 0-.136-.01-.203-.027-1.13-.318-2.097-.986-2.795-1.932-.832-1.125-1.176-2.508-.968-3.893s.942-2.605 2.068-3.438l3.53-2.608c2.322-1.716 5.61-1.224 7.33 1.1.83 1.127 1.175 2.51.967 3.895s-.943 2.605-2.07 3.438l-1.48 1.094c-.333.246-.804.175-1.05-.158-.246-.334-.176-.804.158-1.05l1.48-1.095c.803-.592 1.327-1.463 1.476-2.45.148-.988-.098-1.975-.69-2.778-1.225-1.656-3.572-2.01-5.23-.784l-3.53 2.608c-.802.593-1.326 1.464-1.475 2.45-.15.99.097 1.975.69 2.778.498.675 1.187 1.15 1.992 1.377.4.114.633.528.52.928-.092.33-.394.547-.722.547z"></path><path d="M7.27 22.054c-1.61 0-3.197-.735-4.225-2.125-.832-1.127-1.176-2.51-.968-3.894s.943-2.605 2.07-3.438l1.478-1.094c.334-.245.805-.175 1.05.158s.177.804-.157 1.05l-1.48 1.095c-.803.593-1.326 1.464-1.475 2.45-.148.99.097 1.975.69 2.778 1.225 1.657 3.57 2.01 5.23.785l3.528-2.608c1.658-1.225 2.01-3.57.785-5.23-.498-.674-1.187-1.15-1.992-1.376-.4-.113-.633-.527-.52-.927.112-.4.528-.63.926-.522 1.13.318 2.096.986 2.794 1.932 1.717 2.324 1.224 5.612-1.1 7.33l-3.53 2.608c-.933.693-2.023 1.026-3.105 1.026z"></path></g></svg>'

  img_svg = '<div style="height:5em; width:5em; display:block;"><svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 48 48"><g><path d="M14 11.25H6c-.414 0-.75.336-.75.75s.336.75.75.75h8c.414 0 .75-.336.75-.75s-.336-.75-.75-.75zm0-4H6c-.414 0-.75.336-.75.75s.336.75.75.75h8c.414 0 .75-.336.75-.75s-.336-.75-.75-.75zm-3.25 8H6c-.414 0-.75.336-.75.75s.336.75.75.75h4.75c.414 0 .75-.336.75-.75s-.336-.75-.75-.75z"></path><path d="M21.5 11.25h-3.25v-7C18.25 3.01 17.24 2 16 2H4C2.76 2 1.75 3.01 1.75 4.25v15.5C1.75 20.99 2.76 22 4 22h15.5c1.517 0 2.75-1.233 2.75-2.75V12c0-.414-.336-.75-.75-.75zm-18.25 8.5V4.25c0-.413.337-.75.75-.75h12c.413 0 .75.337.75.75v15c0 .452.12.873.315 1.25H4c-.413 0-.75-.337-.75-.75zm16.25.75c-.69 0-1.25-.56-1.25-1.25v-6.5h2.5v6.5c0 .69-.56 1.25-1.25 1.25z"></path></g></svg></div>'

  def get_expanded_url(link):
    for url in tweet_json['entities']['urls']:
      if url['url'] == link:
        return url['expanded_url']
    return link

  if tweet_json.get('card'):
    card = tweet_json['card']['binding_values']

    link = ''
    if tweet_json['card']['name'] == 'summary' or tweet_json['card']['name'] == 'direct_store_link_app':
      card_type = 1
      link = get_expanded_url(tweet_json['card']['url'])
      title = card['title']['string_value']
      if card.get('description') and card['description'].get('string_value'):
        desc = card['description']['string_value']
      else:
        desc = ''
      img = ''
      img_keys = ['summary_photo_image_small', 'thumbnail_image_large', 'thumbnail']
      for key in img_keys:
        if card.get(key):
          img = '<img style="height:5em; display:block; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}" />'.format(card[key]['image_value']['url'])
      if not img:
        img = img_svg

    elif tweet_json['card']['name'] == 'player':
      card_type = 1
      link = card['player_url']['string_value']
      if 'youtube' in link:
        m = re.match(r'https:\/\/www\.youtube\.com\/embed\/([^#\&\?]{11})', link)
        link = 'https://www.youtube.com/watch?v=' + m.group(1)
      title = card['title']['string_value']
      if card.get('description'):
        desc = card['description']['string_value']
      else:
        desc = ''
      img = '<div style="position:relative; text-align:center;"><img style="height:5em; display:block; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"/><div style="position:absolute; width:32px; height:32px; left:50%; top:50%; transform:translate(-50%,-50%); border:4px solid white; border-radius:9999px; background-color:rgb(29,161,242);"></div><div style="position:absolute; width:24px; height:24px; left:50%; top:50%; transform:translate(-50%,-50%);"><svg viewBox="0 0 24 24"><g><path stroke="white" fill="white" d="M20.436 11.37L5.904 2.116c-.23-.147-.523-.158-.762-.024-.24.132-.39.384-.39.657v18.5c0 .273.15.525.39.657.112.063.236.093.36.093.14 0 .28-.04.402-.117l14.53-9.248c.218-.138.35-.376.35-.633 0-.256-.132-.495-.348-.633z"></path></g></svg></div></div>'.format(card['player_image_large']['image_value']['url'])

    elif tweet_json['card']['name'] == 'summary_large_image':
      card_type = 2 
      link = get_expanded_url(tweet_json['card']['url'])
      title = card['title']['string_value']
      if card.get('description') and card['description'].get('string_value'):
        desc = card['description']['string_value']
      else:
        desc = ''
      img = ''
      img_keys = ['summary_photo_image', 'photo_image_full_size', 'thumbnail_image_large']
      for key in img_keys:
        if card.get(key):
          img = card[key]['image_value']['url']
      if not img:
        img = img_svg
        card_type = 1

    elif 'event' in tweet_json['card']['name']:
      card_type = 2
      link = get_expanded_url(tweet_json['card']['url'])
      title = card['event_title']['string_value']
      desc = card['event_subtitle']['string_value']
      img =  card['event_thumbnail']['image_value']['url']

    elif re.search('poll\dchoice_text_only', tweet_json['card']['name']):
      card_type = 3
      n = 0
      total = 0
      max_count = 0
      n_max = 0
      while 'choice{}_label'.format(n+1) in tweet_json['card']['binding_values']:
        c = int(tweet_json['card']['binding_values']['choice{}_count'.format(n+1)]['string_value'])
        total += c
        n = n + 1
        if c > max_count:
          max_count = c
          n_max = n
      media_html = '<svg xmlns="http://www.w3.org/2000/svg" style="width:95%; height:{}em; margin-left:auto; margin-right:auto;">'.format(2*n+1)
      for i in range(n):
        if i+1 == n_max:
          color = 'rgb(116, 202, 254)'
          font = ' font-weight="bold"'
        else:
          color = 'rgb(196, 207, 214)'
          font = ''
        val = round(100*int(tweet_json['card']['binding_values']['choice{}_count'.format(i+1)]['string_value'])/total, 1)
        label = tweet_json['card']['binding_values']['choice{}_label'.format(i+1)]['string_value']
        media_html += '<g><rect x="0" y="{0}em" width="{1}%" height="1.1em" fill="{2}"></rect><text x="0.5em" y="{3}em"{4}>{5}</text><rect x="{1}%" y="{0}em" width="{6}%" height="1.1em" fill="none"></rect><text x="99%" y="{3}em" text-anchor="end"{5}>{1}%</text></g>'.format(2*i, val, color, 2*i+0.9, font, label, round(100-val, 1))
      if tweet_json['card']['binding_values']['counts_are_final']['boolean_value'] == True:
        label = 'Final results'
      else:
        label = 'Polling in progress'
      media_html += '<g><text x="0" y="{}em" font-size="0.9em">{} votes - {}</text></g></svg>'.format(2*(n+1)-0.5, total, label)

    elif tweet_json['card']['name'] == 'promo_website':
      card_type = 2
      link = card['website_dest_url']['string_value']
      title = card['title']['string_value']
      desc = ''
      img = card['promo_image']['image_value']['url']

    else:
      logger.warning('unknown twitter card name ' + tweet_json['card']['name'])
    
    if card.get('vanity_url'):
      link_text = card['vanity_url']['string_value']
    elif link:
      link_text = urlsplit(link).netloc
    else:
      link_text = ''

    if card_type == 1:
      if desc:
        media_html += '<table style="font-size:0.9em; width:95%; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td rowspan="3" style="padding:0;"><a href="{0}">{1}</a></td><td style="display:-webkit-box; -webkit-line-clamp:1; -webkit-box-orient:vertical; overflow:hidden; padding-left:0.5em;"><a href="{0}">{2}</a></td></tr><tr><td style="display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; padding-left:0.5em;"><small>{3}</small></td></tr><tr><td style="padding-left:0.5em;">{4}<a href="{0}"><small>{5}</small></a></td></tr></table><br />'.format(link, img, title, desc, link_svg, link_text)
      else:
        media_html += '<table style="font-size:0.9em; width:95%; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td rowspan="2" style="padding:0;"><a href="{0}">{1}</a></td><td style="display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; padding-left:0.5em;"><a href="{0}">{2}</a></td></tr><tr><td style="padding-left:0.5em;">{3}<a href="{0}"><small>{4}</small></a></td></tr></table><br />'.format(link, img, title, link_svg, link_text)
    elif card_type == 2:
      if desc:
        media_html += '<div style="border:1px solid black; border-radius:10px;"><a href="{0}"><img width="100%" style="border-top-left-radius:10px; border-top-right-radius:10px;" src="{1}" /></a><div style="padding:0 1em 0 1em;"><b><a href="{0}">{2}</a></b><br /><small>{3}</small><br /><small>{4}&nbsp;<a href="{0}">{5}</a></small></div></div><br />'.format(link, img, title, desc, link_svg, link_text)
      else:
        media_html += '<div style="border:1px solid black; border-radius:10px;"><a href="{0}"><img width="100%" style="border-top-left-radius:10px; border-top-right-radius:10px;" src="{1}" /></a><div style="padding:0 1em 0 1em;"><b><a href="{0}">{2}</a></b><br /><small>{3}&nbsp;<a href="{0}">{4}</a></small></div></div><br />'.format(link, img, title, link_svg, link_text)

  dt = datetime.fromisoformat(tweet_json['created_at'].replace('Z', '+00:00'))
  tweet_time = '{}:{} {}'.format(dt.strftime('%I').lstrip('0'), dt.minute, dt.strftime('%p'))
  tweet_date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  if tweet_json.get('quoted_tweet'):
    media_html += make_tweet(tweet_json['quoted_tweet'], is_quoted=True)

  if tweet_json['user']['verified'] == True:
    verified_svg = '<svg viewBox="0 0 24 24" style="width:0.9em; height:0.9em;"><g><path fill="rgb(29, 161, 242)" d="M22.5 12.5c0-1.58-.875-2.95-2.148-3.6.154-.435.238-.905.238-1.4 0-2.21-1.71-3.998-3.818-3.998-.47 0-.92.084-1.336.25C14.818 2.415 13.51 1.5 12 1.5s-2.816.917-3.437 2.25c-.415-.165-.866-.25-1.336-.25-2.11 0-3.818 1.79-3.818 4 0 .494.083.964.237 1.4-1.272.65-2.147 2.018-2.147 3.6 0 1.495.782 2.798 1.942 3.486-.02.17-.032.34-.032.514 0 2.21 1.708 4 3.818 4 .47 0 .92-.086 1.335-.25.62 1.334 1.926 2.25 3.437 2.25 1.512 0 2.818-.916 3.437-2.25.415.163.865.248 1.336.248 2.11 0 3.818-1.79 3.818-4 0-.174-.012-.344-.033-.513 1.158-.687 1.943-1.99 1.943-3.484zm-6.616-3.334l-4.334 6.5c-.145.217-.382.334-.625.334-.143 0-.288-.04-.416-.126l-.115-.094-2.415-2.415c-.293-.293-.293-.768 0-1.06s.768-.294 1.06 0l1.77 1.767 3.825-5.74c.23-.345.696-.436 1.04-.207.346.23.44.696.21 1.04z"></path></g></svg>'
  else:
    verified_svg = ''

  tweet_url = 'https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_json['id_str'])

  if is_parent or is_reply:
    border = ' border-left:2px solid rgb(196, 207, 214);'
    if is_reply == 1:
      border = ''
    tweet_html = '<tr style="font-size:0.9em;"><td style="width:56px;"><img style="width:48px; height:48px; border-radius:50%;" src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1} · <a style="text-decoration:none;" href="{4}">{5}</a></small></a></td></tr>'.format(tweet_json['user']['profile_image_url_https'], tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_svg, tweet_url, tweet_date)
    tweet_html += '<tr><td colspan="2" style="padding:0 0 0 24px;">'
    tweet_html += '<table style="font-size:0.9em; padding:0 0 0 24px;{}"><tr><td rowspan="3">&nbsp;</td><td>{}</td></tr>'.format(border, text_html)
    tweet_html += '<tr><td>{}</td></tr></table></tr></td>'.format(media_html)
  elif is_quoted:
    tweet_html = '<table style="font-size:0.9em; width:95%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;"><tr><td style="width:36px;"><img style="width:32px; height:32px; border-radius:50%;" src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3} <small>@{1} · <a style="text-decoration:none;" href="{4}">{5}</a></small></a></td></tr>'.format(tweet_json['user']['profile_image_url_https'], tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_svg, tweet_url, tweet_date)
    tweet_html += '<tr><td colspan="2">{}</td></tr>'.format(text_html)
    tweet_html += '<tr><td colspan="2">{}</td></tr></table>'.format(media_html)
  else:
    tweet_html = '<tr><td style="width:56px;"><img style="width:48px; height:48px; border-radius:50%;" src="{0}" /></td><td><a style="text-decoration:none;" href="https://twitter.com/{1}"><b>{2}</b>{3}<br /><small>@{1}</small></a></td></tr>'.format(tweet_json['user']['profile_image_url_https'], tweet_json['user']['screen_name'], tweet_json['user']['name'], verified_svg)
    tweet_html += '<tr><td colspan="2" style="padding:0 0 1em 0;">{}</td></tr>'.format(text_html)
    tweet_html += '<tr><td colspan="2">{}</td></tr>'.format(media_html)
    tweet_html += '<tr><td colspan="2"><a style="text-decoration:none;" href="{}"><small>{} · {}</small></a></td></tr>'.format(tweet_url, tweet_time, tweet_date)

  return tweet_html

def get_tweet_json(tweet_id, save_debug=False):
  tweet_json = utils.get_url_json('https://cdn.syndication.twimg.com/tweet?id={}&lang=en'.format(tweet_id))
  if save_debug:
    with open('./debug/tweet.json', 'w') as fd:
      json.dump(tweet_json, fd, indent=2)
  return tweet_json

def get_content(url, args, save_debug=False):
  tweet_id = ''
  tweet_user = ''
  clean_url = ''

  # url can be just the id
  if url.startswith('https'):
    clean_url = utils.clean_url(url)
    m = re.search('https:\/\/twitter\.com\/([^\/]+)\/statuse?s?\/(\d+)', clean_url)
    if m:
      tweet_user = m.group(1)
      tweet_id = m.group(2)  
    else:
      logger.warning('error determining tweet id in ' + url)
      return None
  elif url.isnumeric():
    tweet_id = url

  tweet_json = get_tweet_json(tweet_id, save_debug)
  if not tweet_json:
    return ''

  if not clean_url:
    tweet_user = tweet_json['user']['screen_name']
    clean_url = 'https://twitter.com/{}/status/{}'.format(tweet_user, tweet_id)

  content_html = '<table style="width:80%; min-width:260px; max-width:550px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'

  item = {}
  item['id'] = tweet_id
  item['url'] = clean_url
  item['author'] = {}
  item['author']['name'] = tweet_user

  if not tweet_json['id_str'] in clean_url:
    # Retweet
    item['title'] = '{} retweeted: {}'.format(tweet_user, tweet_json['text'])
    retweet_svg = '<svg viewBox="0 0 24 24" style="width:0.9em; height:0.9em;"><g><path d="M23.615 15.477c-.47-.47-1.23-.47-1.697 0l-1.326 1.326V7.4c0-2.178-1.772-3.95-3.95-3.95h-5.2c-.663 0-1.2.538-1.2 1.2s.537 1.2 1.2 1.2h5.2c.854 0 1.55.695 1.55 1.55v9.403l-1.326-1.326c-.47-.47-1.23-.47-1.697 0s-.47 1.23 0 1.697l3.374 3.375c.234.233.542.35.85.35s.613-.116.848-.35l3.375-3.376c.467-.47.467-1.23-.002-1.697zM12.562 18.5h-5.2c-.854 0-1.55-.695-1.55-1.55V7.547l1.326 1.326c.234.235.542.352.848.352s.614-.117.85-.352c.468-.47.468-1.23 0-1.697L5.46 3.8c-.47-.468-1.23-.468-1.697 0L.388 7.177c-.47.47-.47 1.23 0 1.697s1.23.47 1.697 0L3.41 7.547v9.403c0 2.178 1.773 3.95 3.95 3.95h5.2c.664 0 1.2-.538 1.2-1.2s-.535-1.2-1.198-1.2z"></path></g></svg>'
    content_html += '<tr><td colspan="2">{0}&nbsp;<small><a style="text-decoration:none;" href="https://twitter.com/{1}">@{1}</a> retweeted</small></td></tr>'.format(retweet_svg, tweet_user)

    # Get the real tweet so we can get the reply thread
    tweet_json = get_tweet_json(tweet_json['id_str'])
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

  # Find the conversation thread (replies from the same user)
  search_scraper = None
  try:
    query = 'from:{} conversation_id:{} (filter:safe OR -filter:safe)'.format(tweet_user, tweet_id)
    search_scraper = sntwitter.TwitterSearchScraper(query)
  except Exception as e:
    logger.warning('TwitterSearchScraper exception {} in {}'.format(e.__class__, clean_url))

  if search_scraper:
    search_items = None
    try:
      search_items = search_scraper.get_items()
    except Exception as e:
      logger.warning('TwitterSearchScraper.get_items exception {} in {}'.format(e.__class__, clean_url))

    if search_items:
      tweet_replies = []
      for i,tweet in enumerate(search_items):
        tweet_json = get_tweet_json(tweet.id)
        if tweet_json.get('in_reply_to_screen_name') and tweet_json['in_reply_to_screen_name'] == tweet_user:
          tweet_replies.append(tweet_json)
      for i,tweet_json in reversed(list(enumerate(tweet_replies))):
        content_html += make_tweet(tweet_json, is_reply=i+1)

  content_html += '</table>'
  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  user = ''
  if args.get('url'):
    m = re.search('https:\/\/twitter\.com\/([^\/]+)', args['url'])
    if m:
      user = m.group(1)
    else:
      logger.warning('unable to parse tweet user name ' + args['url'])
  elif args.get('user'):
    user = args['user']
  else:
    logger.warning('missing arguement for user name')
  if not user:
    return None  

  n = 0
  items = []
  feed = utils.init_jsonfeed(args)
  #for tweet in sntwitter.TwitterSearchScraper(f'from:' + user).get_items():
  query = 'from:{}'.format(user)
  if args.get('age'):
    query += ' within_time:{}h'.format(args['age'])
  for i,tweet in enumerate(sntwitter.TwitterSearchScraper(query).get_items()):
    item = get_content('https://twitter.com/{}/status/{}'.format(user, tweet.id), args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  #tweets_list.append([tweet.date, tweet.id, tweet.content, tweet.username])
  return feed