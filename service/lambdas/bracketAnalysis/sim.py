from bs4 import BeautifulSoup
import requests
import time
import numpy as np
from random import random
from utils import (
    rounds, round_matchups, matchup_sequence,
    matchup_score_value, matchup_max_seeds
)


def fetch_bracket_key(id='72858746', year='2023'):
    url = 'https://fantasy.espn.com/tournament-challenge-bracket/%s/en/entry?entryID=%s' % (
        str(year), str(id)
    )
    req = requests.get(url)
    soup = BeautifulSoup(req.content, 'lxml')

    m_classes = ['.m_' + str(i+1) for i in range(63)]
    matchups = [soup.select(mc)[0] for mc in m_classes]

    selections = {}
    teams = {}
    for i, m in enumerate(matchups):
        matchup = i + 1
        loc1 = 0
        loc2 = 2 if matchup >= 33 else 1

        name1 = m.select('.name')[loc1].text
        abbrev1 = m.select('.abbrev')[loc1].text
        seed1 = m.select('.seed')[loc1].text
        name2 = m.select('.name')[loc2].text
        abbrev2 = m.select('.abbrev')[loc2].text
        seed2 = m.select('.seed')[loc2].text
        win_select = m.select('.winner')
        winner = win_select[0].select('.abbrev')[0].text if win_select else ''

        selections[i+1] = {
            'team1': abbrev1,
            'team2': abbrev2,
            'selected': winner
        }
        if matchup <= 32:
            teams[abbrev1] = {
                'name': name1,
                'abbrev': abbrev1,
                'seed': int(seed1),
            }
            teams[abbrev2] = {
                'name': name2,
                'abbrev': abbrev2,
                'seed': int(seed2),
            }

    key = selections
    sorted_keys = sorted(teams, key=lambda x: (
        teams[x]['seed'], teams[x]['abbrev']))
    teams = {t: teams[t] for t in sorted_keys}
    return key, teams


def get_eliminated_teams(key):
    eliminated = []
    for x in key.values():
        if x['selected']:
            if x['selected'] == x['team1']:
                eliminated.append(x['team2'])
            elif x['selected'] == x['team2']:
                eliminated.append(x['team1'])
    return eliminated


def apply_alt_display_names(brackets):
    display_names = [b['display_name'] for b in brackets.values()]
    for b in brackets:
        dname = brackets[b]['display_name']
        bname = brackets[b]['bracket_name']
        if display_names.count(dname) > 1:
            brackets[b]['display_name'] = bname[:12].strip()


def get_bracket_score(bracket, key, eliminated, round='NCG'):
    score = 0
    max_score = 0
    last_matchup = round_matchups[round][-1]
    for i in range(1, last_matchup + 1):
        winner = key[i]['selected']
        if winner:
            if bracket['selections'][i]['selected'] == winner:
                score += matchup_score_value[i]
        else:
            if bracket['selections'][i]['selected'] not in eliminated:
                max_score += matchup_score_value[i]

    max_score += score
    return score, max_score


def get_bracket_upsets(bracket, key, teams):
    upsets_chosen = 0
    upsets_correct = 0
    upsets_played = 0
    for i in range(1, 64):
        selected = bracket['selections'][i]['selected']
        selected_seed = teams[selected]['seed']
        winner = key[i]['selected']

        if selected_seed > matchup_max_seeds[i]:
            upsets_chosen += 1
            if winner:
                upsets_played += 1
                if selected == winner:
                    upsets_correct += 1

    return upsets_chosen, upsets_correct, upsets_played


def sim_game(t1, t2, teams):
    diff = teams[t2]['seed'] - teams[t1]['seed']
    pr = 0.5 + 0.028*(diff)
    return t1 if random() < pr else t2


def sim_bracket(key, teams):
    sim = {m: {x: key[m][x] for x in key[m]} for m in key}

    for m in sim:
        if not sim[m]['selected']:
            result = sim_game(sim[m]['team1'], sim[m]['team2'], teams)
            sim[m]['selected'] = result
            if m < 63:
                next_matchup = matchup_sequence[m]['matchup']
                slot = matchup_sequence[m]['slot']
                sim[next_matchup][slot] = result

    return sim


def group_simulation(brackets, key, teams, eliminated, N=10000):
    sim_data = {
        b: {r: {'scores': [], 'ranks': []} for r in rounds}
        for b in brackets
    }
    for _ in range(N):
        sim = sim_bracket(key, teams)
        scores = {
            b: {
                r: get_bracket_score(brackets[b], sim, eliminated, r)[0]
                for r in rounds
            } for b in brackets
        }
        ranks = {
            r: sorted(
                scores,
                key=lambda x: (scores[x][r], scores[x]['NCG'], random()),
                reverse=True
            )
            for r in rounds
        }
        for b in brackets:
            for r in rounds:
                sim_data[b][r]['scores'].append(scores[b][r])
                sim_data[b][r]['ranks'].append(ranks[r].index(b) + 1)

    return sim_data


def round_pct(x):
    if x > 99.999:
        return 100.0
    elif x < 0.001:
        return 0.0
    else:
        return min(max(x, 0.1), 99.9)


# MAIN ANALYSIS FUNCTION

def group_analysis(brackets, sim_results, key, eliminated, teams):

    # current scores
    current_scores = [
        {
            'name': brackets[b]['display_name'],
            'pts': get_bracket_score(brackets[b], key, eliminated)[0],
            'max': get_bracket_score(brackets[b], key, eliminated)[1],
        } for b in brackets
    ]
    current_scores = sorted(
        current_scores,
        key=lambda x: (x['pts'], x['max']),
        reverse=True
    )

    # projection board (by round)
    projection_board = {
        r: [
            {
                'name': brackets[b]['display_name'],
                'pts': round(np.mean(sim_results[b][r]['scores'])),
                'win': round_pct(np.mean([x == 1 for x in sim_results[b][r]['ranks']]) * 100),
            } for b in brackets
        ] for r in rounds
    }
    for r in projection_board:
        projection_board[r] = sorted(
            projection_board[r],
            key=lambda x: x['win'],
            reverse=True
        )

    # projected rank
    rankings = [
        {
            'name': brackets[b]['display_name'],
            'avg': round(np.mean(sim_results[b]['NCG']['ranks']), 1),
            'worst': max(sim_results[b]['NCG']['ranks']),
            'best': min(sim_results[b]['NCG']['ranks']),
        } for b in brackets
    ]
    rankings = sorted(
        rankings,
        key=lambda x: (x['avg'], x['best']),
    )

    # upsets chosen
    upsets_chosen = [
        {
            'name': brackets[b]['display_name'],
            'chosen': get_bracket_upsets(brackets[b], key, teams)[0],
            'n_correct': get_bracket_upsets(brackets[b], key, teams)[1],
            'correct': '%d/%d' % (
                get_bracket_upsets(brackets[b], key, teams)[1],
                get_bracket_upsets(brackets[b], key, teams)[2],
            ),
        } for b in brackets
    ]
    upsets_chosen = sorted(
        upsets_chosen,
        key=lambda x: (x['chosen'], x['n_correct']),
        reverse=True
    )

    # team info
    team_info = {
        t: {
            **teams[t],
            'eliminated': t in eliminated,
            'display_name': teams[t]['name'] if len(teams[t]['name']) < 11 else t,
            'display_seed': '%s (%d)' % (
                teams[t]['name'] if len(teams[t]['name']) < 11 else t,
                teams[t]['seed'],
            )
        } for t in teams
    }

    # most popular teams
    team_popularity = [
        {
            'team': team_info[t]['display_seed'],
            'avg': round(
                np.mean(
                    [sum([m['selected'] == t for m in b['selections'].values()])
                     for b in brackets.values()]
                ),
                1
            ),
        } for t in teams
    ]
    team_popularity = sorted(
        team_popularity,
        key=lambda x: x['avg'],
        reverse=True
    )

    # return analysis
    timestamp = round(time.time())
    return {
        'timestamp': timestamp,
        'current_scores': current_scores,
        'projection_board': projection_board,
        'rankings': rankings,
        'upsets_chosen': upsets_chosen,
        'team_info': team_info,
        'team_popularity': team_popularity
    }
