#!/usr/bin/env python3

import sys
import http.client
import json
import time
import math
from datetime import datetime
import pickle
import os

tau = .2
eplison = 0.000001

def req_success(resp):
    if resp.status == 200:
        return True
    print("Request failed")
    print(resp.status, resp.reason)
    info_body = resp.read()
    print(info_body)
    return False
    
def glicko_g(phi):
    return 1/math.sqrt(1+3*(phi**2/math.pi**2))

def glicko_e(mu, mu_j, phi_j):
    return 1/(1+math.exp(-glicko_g(phi_j)*(mu-mu_j)))

def glicko_f(x, delta, phi, v, t, a):
    nom = (delta ** 2) - (phi ** 2) - v - math.exp(x)
    nom *= math.exp(x)
    denom = (phi ** 2) + v + math.exp(x)
    denom = denom ** 2
    denom *= 2
    nom_2 = x - a
    denom_2 = tau ** 2
    term_1 = nom / denom
    term_2 = nom_2 / denom_2
    return term_1 - term_2

def get_driver_dict():

    driver_dict_path = ".driver_dict.pkl"
    rounds_dict_path = ".rounds_dict.pkl"
    dict_max_age = 259200
    data_date = 0
    driver_dict = {}
    rounds_dict = {}

    if os.path.isfile(driver_dict_path) and os.path.isfile(rounds_dict_path):
        driver_dict_mtime = os.path.getmtime(driver_dict_path)
        data_date = driver_dict_mtime
        round_dict_mtime = os.path.getmtime(rounds_dict_path)
        now = time.time()
        if (now - driver_dict_mtime) < dict_max_age and (now - round_dict_mtime) < dict_max_age:
            driver_dict_file = open(driver_dict_path, "rb")
            rounds_dict_file = open(rounds_dict_path, "rb")
            driver_dict = pickle.load(driver_dict_file)
            driver_dict_file.close()
            rounds_dict = pickle.load(rounds_dict_file)
            rounds_dict_file.close()
            return (driver_dict, rounds_dict, data_date)

    rounds_dict["first_year"] = 1950
    rounds_dict["first_race"] = 1
    rounds_dict["last_year"] = -1
    rounds_dict["last_race"] = -1
    rounds_dict["last_race_name"] = ""
    
    conn = http.client.HTTPSConnection("ergast.com")
    if rounds_dict["last_year"] < 0 or rounds_dict["last_race"] < 0:
        conn.request("GET", "/api/f1/current/last.json")
        req_curr_year = conn.getresponse()
        if not req_success(req_curr_year):
            return None
        data_curr_year = req_curr_year.read()
        json_curr_year = json.loads(data_curr_year)["MRData"]
        if rounds_dict["last_year"] < 0:
            rounds_dict["last_year"] = int(json_curr_year["RaceTable"]["season"])
        if rounds_dict["last_race"] < 0:
            rounds_dict["last_race"] = int(json_curr_year["RaceTable"]["round"])
            rounds_dict["last_race_name"] = json_curr_year["RaceTable"]["Races"][0]["raceName"]
    
    for year in range(rounds_dict["first_year"], rounds_dict["last_year"]+1):
        conn.request("GET", "/api/f1/{0}.json".format(year))
        req_all = conn.getresponse()
        if not req_success(req_all):
            continue
        data_all = req_all.read()
        json_all = json.loads(data_all)
        races = json_all["MRData"]["RaceTable"]["Races"]
        num_races = len(races)
        start_race = 1
        if year == rounds_dict["last_year"]:
            num_races = rounds_dict["last_race"]
        if year == rounds_dict["first_year"]:
            start_race = rounds_dict["first_race"]
        rounds_dict[year] = {}
        for round in range(start_race, num_races+1):
            time.sleep(.1)
            conn.request("GET", "/api/f1/{0}/{1}/results.json".format(year, round))
            req_round = conn.getresponse()
            if not req_success(req_round):
                continue
            data_round = req_round.read()
            print(year, round, "driver_dict")
            json_round = json.loads(data_round)
            round_info = json_round["MRData"]["RaceTable"]["Races"][0]
            rounds_dict[year][round] = round_info
            if round_info["raceName"] == "Indianapolis 500":
                continue
            round_date = datetime.strptime(round_info["date"], "%Y-%m-%d")
            round_results = round_info["Results"]
            for i in round_results:
                driver_data = i["Driver"]
                driver_id = driver_data["driverId"]
                if driver_id not in driver_dict:
                    driver_dict[driver_id] = {"name" : "{0} {1}".format(driver_data["givenName"], driver_data["familyName"]), "first_race": round_date, "last_race": round_date, "race_num": 1, "rating": 1500, "rd": 350, "vol": 0.06, "peak_rating": 0, "peak_rd": 0, "peak_vol" : 0, "avg_rating": 0, "ratings_hist": {}, "ratings": 0}
                else:
                    driver_dict[driver_id]["last_race"] = round_date
                    driver_dict[driver_id]["race_num"] += 1
    conn.close()
    driver_dict_file = open(driver_dict_path, "wb")
    rounds_dict_file = open(rounds_dict_path, "wb")
    pickle.dump(driver_dict, driver_dict_file)
    driver_dict_file.close()
    pickle.dump(rounds_dict, rounds_dict_file)
    rounds_dict_file.close()
    data_date = os.path.getmtime(driver_dict_path)
    return (driver_dict, rounds_dict, data_date)

def get_stats(driver_dict, rounds_dict):
    for year in range(rounds_dict["first_year"], rounds_dict["last_year"]+1):
        num_races = len(rounds_dict[year])
        start_race = 1
        if year == rounds_dict["last_year"]:
            num_races = rounds_dict["last_race"]
        if year == rounds_dict["first_year"]:
            start_race = rounds_dict["first_race"]
        for round in range(start_race, num_races+1):
            print(year, round, "get_stats")
            round_info = rounds_dict[year][round]
            if round_info["raceName"] == "Indianapolis 500":
                continue
            round_results = round_info["Results"]
            round_date = datetime.strptime(round_info["date"], "%Y-%m-%d")
            race_positions = {}
            min_laps = math.ceil(float(round_results[0]["laps"]))
            for i in round_results:
                driver_data = i["Driver"]
                driver_id = driver_data["driverId"]
                position = int(i["position"])
                if not i["positionText"].isnumeric():
                    pos_text = i["positionText"]
                    if pos_text == "R" and int(i["laps"]) < min_laps:
                        position = 40
                    elif pos_text != "R":
                        position = 40
                race_positions[driver_id] = position
            for i in driver_dict:
                if i in race_positions:
                    continue
                elif not isinstance(driver_dict[i], dict):
                    continue
                else:
                    if driver_dict[i]["last_race"] > round_date and driver_dict[i]["first_race"] < round_date:
                        race_positions[i] = -1
            new_stats = {}
            for i in race_positions.items():
                curr_id = i[0]
                curr_pos = int(i[1])
                old_stats = driver_dict[curr_id]
                new_stats[curr_id] = {"rating": old_stats["rating"], "rd": old_stats["rd"], "vol": old_stats["vol"]}
                curr_mu = (old_stats["rating"] - 1500)/173.7178
                curr_phi = old_stats["rd"]/173.7178
                new_mu = curr_mu
                new_phi = curr_phi
                if curr_pos > 0:
                    v_sum = 0
                    delta_sum = 0
                    for j in race_positions.items():
                        score = 0
                        opp_id = j[0]
                        opp_pos = int(j[1])
                        if curr_id != opp_id and opp_pos > 0:
                            curr_pos = int(i[1])
                            try:
                                opp_mu = (driver_dict[opp_id]["rating"] - 1500)/173.7178
                                opp_phi = driver_dict[opp_id]["rd"]/173.7178
                            except:
                                print(opp_id + " missing")
                                continue
                            opp_g = glicko_g(opp_phi)
                            opp_e = glicko_e(curr_mu, opp_mu, opp_phi)
                            v_sum += (opp_g**2)*opp_e*(1-opp_e)
                            if curr_pos < opp_pos:
                                score = 1
                            elif curr_pos == opp_pos:
                                score = .5
                            else:
                                score = 0
                            delta_sum += opp_g*(score - opp_e)
                    curr_v = 1/v_sum
                    curr_delta = curr_v * delta_sum
                    curr_sigma = old_stats["vol"]
                    old_sigma_ln = math.log(curr_sigma**2)
                    curr_A = math.log(curr_sigma**2)
                    curr_B = 0
                    if curr_delta**2 > (curr_phi**2 + curr_v):
                        curr_B = math.log(curr_delta**2 - curr_phi**2 - curr_v)
                    else:
                        k = 1
                        while glicko_f((curr_A - k*tau), curr_delta, curr_phi, curr_v, tau, old_sigma_ln) < 0:
                            k += 1
                        curr_B = curr_A - k*tau
                    curr_fA = glicko_f(curr_A, curr_delta, curr_phi, curr_v, tau, old_sigma_ln)
                    curr_fB = glicko_f(curr_B, curr_delta, curr_phi, curr_v, tau, old_sigma_ln)
                    while abs(curr_B - curr_A) > eplison:
                        curr_C = curr_A + ((curr_A - curr_B)*curr_fA)/(curr_fB - curr_fA)
                        curr_fC = glicko_f(curr_C, curr_delta, curr_phi, curr_v, tau, old_sigma_ln)
                        if curr_fC * curr_fB < 0:
                            curr_A = curr_B
                            curr_fA = curr_fB
                        else:
                            curr_fA /= 2
                        curr_B = curr_C
                        curr_fB = curr_fC
                    new_sigma = math.exp(curr_A / 2)
                    new_pre_phi = math.sqrt((curr_phi ** 2) + (new_sigma ** 2))
                    new_phi = 1/math.sqrt((1/(new_pre_phi ** 2)) + (1/curr_v))
                    new_mu = curr_mu + (new_phi ** 2) * (delta_sum)
                else:
                    curr_sigma = old_stats["vol"]
                    new_phi = 1/math.sqrt((1/(curr_phi ** 2)) + (1/(curr_sigma**2)))
                new_rating = (173.7178 * new_mu) + 1500
                new_rd = 173.7178 * new_phi
                new_stats[curr_id]["rating"] = new_rating
                new_stats[curr_id]["rd"] = new_rd
                new_stats[curr_id]["vol"] = new_sigma
            for update_id in new_stats:
                if new_stats[update_id]["rating"] > driver_dict[update_id]["peak_rating"]:
                    driver_dict[update_id]["peak_rating"] = new_stats[update_id]["rating"]
                    driver_dict[update_id]["peak_rd"] = new_stats[update_id]["rd"]
                    driver_dict[update_id]["peak_vol"] = new_stats[update_id]["vol"]
                driver_dict[update_id]["rating"] = new_stats[update_id]["rating"]
                driver_dict[update_id]["avg_rating"] = driver_dict[update_id]["avg_rating"] + ((new_stats[update_id]["rating"] - driver_dict[update_id]["avg_rating"])/(driver_dict[update_id]["ratings"] + 1))
                driver_dict[update_id]["ratings"] += 1
                driver_dict[update_id]["rd"] = new_stats[update_id]["rd"]
                driver_dict[update_id]["vol"] = new_stats[update_id]["vol"]
                driver_dict[update_id]["ratings_hist"][round_date] = {"rating": new_stats[update_id]["rating"], "rd": new_stats[update_id]["rd"], "vol": new_stats[update_id]["vol"]}
    return driver_dict
    
if __name__ == "__main__":
    out_path_common = "/srv/http/mekapaedia.com/f1/"
    out_path = {}
    out_path["overall"] = "index.html"
    out_path["final"] = "final.html"
    out_path["peak"] = "peak.html"
    out_path["average"] = "avg.html"
    out_path["name"] = "name.html"
    
    (driver_dict, round_dict, data_date) = get_driver_dict()
    data_date_str = datetime.utcfromtimestamp(data_date).strftime('%-I:%M:%S %p (UTC%z) %a %b %-m, %Y')
    if driver_dict is None:
        print("Invalid driver dictionary")
        sys.exit(1)         
    driver_dict = get_stats(driver_dict, round_dict)
    del_list = []
    for driver_id in driver_dict:
        if not isinstance(driver_dict[driver_id], dict):
            del_list.append(driver_id)
        elif driver_dict[driver_id]["race_num"] < 4:
            del_list.append(driver_id)
        else:
            driver_dict[driver_id]["combo_rating"] = (driver_dict[driver_id]["peak_rating"] + driver_dict[driver_id]["avg_rating"] + driver_dict[driver_id]["rating"])/3
    for driver_id in del_list:
        del driver_dict[driver_id]

    for sort_type, file_name in out_path.items():
        rating_type = "combo_rating"
        not_name = True
        if sort_type == "final":
            rating_type = "rating"
        elif sort_type == "peak":
            rating_type = "peak_rating"
        elif sort_type == "average":
            rating_type = "avg_rating"
        elif sort_type == "name":
            rating_type = "name"
            not_name = False

        sorted_dict = dict(sorted(driver_dict.items(), key=lambda x: x[1][rating_type], reverse=not_name))

        html_out_path = "{}{}".format(out_path_common, file_name)
        html_out_file = open(html_out_path, "w")
        html_out_file.write("<!DOCTYPE html>\n")
        html_out_file.write("<html lang=\"en\">\n")
        html_out_file.write("\n")
        html_out_file.write("<head>\n")
        html_out_file.write("<meta charset=\"UTF-8\">\n")
        html_out_file.write("<title>\n")
        html_out_file.write("Mekapaedia - F1 driver ratings\n")
        html_out_file.write("</title>\n")
        html_out_file.write("\n")
        html_out_file.write("<link rel=\"stylesheet\" type=\"text/css\" href=\"../styles.css\">")
        html_out_file.write("\n")
        html_out_file.write("</head>\n")
        html_out_file.write("\n")
        html_out_file.write("<body>\n")
        html_out_file.write("<div id=bodytext>\n")
        html_out_file.write("\n")
        html_out_file.write("<div id=header>\n")
        html_out_file.write("<h1><a href=\"../index.html\">Mekapaedia</a></h1>")
        html_out_file.write("<strong><a href=\"../about.html\">about me</a> - <a href=\"../other.html\">other stuff</a> - <a href=\"../index.html\">contact/link tree</a></strong>\n")
        html_out_file.write("</div>\n")
        html_out_file.write("<br><br>\n")
        html_out_file.write("<div id=innertext>\n")
        html_out_file.write("<h2>F1 Driver Glicko-2 ratings</h2>\n")
        html_out_file.write("The table below is a set of driver ratings using the <a href=\"http://www.glicko.net/glicko/glicko2.pdf\">Glicko-2 ratings system</a>.<br><br>\n")
        html_out_file.write("These generated ratings use a tau of {0} - in the document for Glicko-2 Professor Glickman suggests a tau as low as .2 for a game with regular \"unexpected\" results (i.e.: a player with a significantly lower skill beats a higher skilled player), and it seems to work well for F1 where the results are dependent on many more factors than just driver skill.<br><br>\n".format(tau))
        html_out_file.write("The ratings system effectly treats each race as a round-robin tournament: so each driver's rating is based not just on if they win, but how many drivers they beat and how skilled those drivers are. Disqualification, retirement with less than 80% of laps completed, failure to (pre-)qualify, exclusion, or \"not counted\" are all treated as a shared last position.<br>\n")
        html_out_file.write("The final score is an average of the running average Glicko-2 score, peak Glicko-2 score, and most recent (which is important as Glicko-2 is intended to be a convergent algorithm) Glicko-2 score. This seems to give a good mix of rewarding consistency, but still rewarding rare exceptional performances (like Giancarlo Baghetti). Qualifying, Non-Championship races, and races in other series (like touring cars or Le Mans) are not counted as the data isn't readily available.<br><br>\n")
        html_out_file.write("The source for the data is the excellent <a href=\"http://ergast.com/mrd/\">Ergast F1 Developer API</a>, which is well worth a look if you are interested in F1 data.<br><br>\n")
        html_out_file.write("<b>Important note:</b> I am not a statistician nor a mathematician. I cannot guarantee <i>any</i> statistical properties regarding these results. I just like data analysis and can write small python scripts. Take them with a grain of salt.<br><br>\n")
        html_out_file.write("Data current as of {0} ({1} {2})<br><br>\n".format(data_date_str, round_dict["last_year"], round_dict["last_race_name"]))
        html_out_file.write("<table style=\"width:100%\">\n")
        html_out_file.write("<tr>\n")
        html_out_file.write("<th>Position</th>\n")
        html_out_file.write("<th><a href=\"./{}\">Name</a></th>\n".format(out_path["name"]))
        html_out_file.write("<th><a href=\"./{}\">Overall Score</a></th>\n".format(out_path["overall"]))
        html_out_file.write("<th><a href=\"./{}\">Final Glicko-2</a></th>\n".format(out_path["final"]))
        html_out_file.write("<th><a href=\"./{}\">Peak Glicko-2</a></th>\n".format(out_path["peak"]))
        html_out_file.write("<th><a href=\"./{}\">Average Glicko-2</a></th>\n".format(out_path["average"]))
        html_out_file.write("</tr>\n")
        position = 0
        for i in sorted_dict:
            position += 1
            html_out_file.write("<tr>\n")
            html_out_file.write("<td>{0}</td>\n".format(position))
            html_out_file.write("<td>{0}</td>\n".format(sorted_dict[i]["name"]))
            html_out_file.write("<td>{0}</td>\n".format(round(sorted_dict[i]["combo_rating"], 2)))
            html_out_file.write("<td>{0}</td>\n".format(round(sorted_dict[i]["rating"], 2)))
            html_out_file.write("<td>{0}</td>\n".format(round(sorted_dict[i]["peak_rating"], 2)))
            html_out_file.write("<td>{0}</td>\n".format(round(sorted_dict[i]["avg_rating"], 2)))
            html_out_file.write("</tr>\n")
        html_out_file.write("</table>")
        html_out_file.write("<br><br>\n")
        html_out_file.write("</div>\n")
        html_out_file.write("</div>\n")
        html_out_file.write("</body>\n")
        html_out_file.write("\n")
        html_out_file.write("</html>")
        html_out_file.close()
