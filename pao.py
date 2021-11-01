import sys
reload(sys)  # Reload does the trick!
sys.setdefaultencoding('utf-8')
import cmd
import pickle
import os.path
import os
import datetime
import time
import pprint
import random
from tabulate import tabulate
import csv
import copy

class PetanqueTournament(cmd.Cmd):
    """Simple command processor example."""

    tournament = dict(
        name="",
        teams=dict(),
        created_at=datetime.datetime.utcnow(),
        modified_at=datetime.datetime.utcnow(),
        court_map = dict(a=(1,10), b=(0,0))
        )




    ##################################
    ####### private functions    #####
    ##################################
    def read_csv(self, filename):
        with open(filename, 'rb') as csvfile:
            spamreader = csv.reader(csvfile, dialect="excel")
            idx = 0
            for idx, row in enumerate(spamreader):
                if idx > 0:
                    # loc = row[3] if row[3] == row[5] else "%s, %s" %(row[3], row[5])
                    team = "%s & %s " % (row[2], row[6])
                    team = unicode(team, "utf-8")
                    group = row[1]
                    num = row[0]
                    line = "%s %s %s" % (num, group,  team)
                    # print line
                    self.do_team(line)
            print("Imported ... %d teams" %idx)

    def is_court_a(self, num):
        if num >= self.tournament["court_map"]["a"][0] and num <= self.tournament["court_map"]["a"][1]:
            return True
        return False

    def is_court_b(self, num):
        if num >= self.tournament["court_map"]["b"][0] and num <= self.tournament["court_map"]["b"][1]:
            return True

        return False

    def tournament_loaded(self):
        if self.tournament.get("name"):
            return True

        print("First load a tournament with `use` [name]")
        return False

    def export_csv(self, filename, data):
        f = open(filename, 'wt')
        try:
            writer = csv.writer(f)
            for r in data:
                writer.writerow(r)
        finally:
            f.close()

        print("Exported ...", filename)

    def save(self):
        file_path='./%s.p' % self.tournament.get("name")
        self.tournament["modified_at"] =datetime.datetime.utcnow()
        pickle.dump( self.tournament, open( file_path, "wb" ) )

    def set_prompt(self):
        self.prompt = self.tournament.get("name") +' >> '

    def format_team_game(self, tid, team, rnd):
        oid = team["games"][rnd]
        opp = self.tournament["teams"][oid]
        return [tid, team["name"], "vs", oid, opp["name"], "court", team["courts"][rnd]]


    def show_rnd(self, rnd):
        table = [self.format_team_game(k,v, rnd) for k,v in self.tournament["teams"].iteritems()]
        table.sort()
        if rnd >= 0:
            print("Round", rnd+1)
        print(tabulate(table, tablefmt="grid"))

    def remove_rnd(self, rnd):
        for k,v in self.tournament["teams"].iteritems():
            if rnd == -1:
                if len(v['games']) > 0:
                    g = v['games'][:-1]

                    cn = v['courts'][-1]
                    c = v['courts'][:-1]

                    self.tournament["teams"][k]["games"] = g
                    self.tournament["teams"][k]["courts"] = c

                    if self.is_court_b(cn):
                        self.tournament["teams"][k]["played_b"] = 0
            else:
                if len(v['games']) > rnd:
                    g = v['games']
                    c = v['courts']
                    cn = c[rnd]
                    del g[rnd]
                    del c[rnd]
                    self.tournament["teams"][k]["games"] = g
                    self.tournament["teams"][k]["courts"] = c
                    if self.is_court_b(cn):
                        self.tournament["teams"][k]["played_b"] = 0


    def export_rnd(self, rnd):
        data = []
        score = []
        team_ids = []

        teams = copy.deepcopy(self.tournament["teams"])

        
        for k,v in teams.iteritems():
            oid = v["games"][rnd]
            opp = self.tournament["teams"][oid]
            crt = v["courts"][rnd]
            row = [k, v["name"], "vs", oid, opp["name"], "court", crt]
            data.append(row)

            if k not in team_ids:
                row = [crt, k, 0, "" , oid, 0]
                score.append(row)
                team_ids = team_ids + [k, oid]

        # for game poster
        utime = time.time()
        data.sort()
        filename = "%s_round_%s_%d.csv" % (self.tournament["name"], rnd+1, utime)
        self.export_csv(filename, data)
        
        # for game scoring
        filename = "%s_score_round_%s_%d.csv" % (self.tournament["name"], rnd+1, utime)
        score.sort()
        self.export_csv(filename, score)

    def court_map(self):
        courts =[]
        courts_a = []

        # get all courts and courts A
        for k,v in self.tournament["court_map"].iteritems():
            for i in range(v[0],v[1]+1):
                if k == "a":
                    courts_a.append(i)
                courts.append(i)

        return courts, courts_a

    def create_round(self, line):
        games = []

        is_b = set()
        not_b = set()

        team_ids = set()
        groups = dict()

        if len(self.tournament["teams"]) % 2 == 1:
            last = sorted(self.tournament["teams"].keys())[-1]
            args = "%d EUR BYE-%d" % (last+1, last+1)
            self.do_team(args)

        # get all courts and courts A
        courts, courts_a = self.court_map()
        # print "%s %s " % (courts, courts_a)

        teams = self.tournament["teams"]
        for k, v in teams.iteritems():
            team_ids.add(k)
            g = v.get("group")
            if g in groups:
                groups[g].add(k)
            else:
                groups[g] = set([k])

            if v.get("played_b") > 0:
                is_b.add(k)
            else:
                not_b.add(k)

        team_scheduled = set()
        # Let's do the scheduled for teams that played_b


        if "-f" in line:
            not_b = not_b | is_b
            is_b = set()

        for tid in is_b:
            if tid not in team_scheduled:
                team = self.tournament["teams"][tid]
                teams_played = set(team["games"])

                my_group = groups[team["group"]]
                possible_teams = set(team_ids) - (team_scheduled | teams_played | my_group | is_b)
                t1, t2 = self.schedule_game(tid, possible_teams, team_scheduled)

                if "-d" in line:
                    print("[DEBUG] B", tid, t1, t2, possible_teams)

                if t1 == None:
                    return []

                courts_t1 = self.tournament["teams"][t1]["courts"]
                courts_t2 = self.tournament["teams"][t2]["courts"]
                possible_courts = list(set(courts_a) - (set(courts_t1) | set(courts_t2)))

                random.shuffle(possible_courts)

                c = possible_courts.pop()
                courts_a.remove(c)
                courts.remove(c)
                games.append((t1, t2, c))

        # Let's do the rest
        not_b_list = list(not_b)
        random.shuffle(not_b_list)

        for tid in not_b_list:
            if tid not in team_scheduled:
                team = self.tournament["teams"][tid]
                teams_played = set(team["games"])
                # courts_played = set(team["courts"])
                my_group = groups[team["group"]]

                possible_teams = set(team_ids) - (team_scheduled | teams_played | my_group)
                t1, t2 = self.schedule_game(tid, possible_teams, team_scheduled)

                if "-d" in line:
                    print("[DEBUG] A", tid, t1, t2, possible_teams)

                if t1 == None:
                    return []

                possible_courts = []
                
                if line == "-f":
                    if len(courts_a) > 0:
                        possible_courts = list(set(courts_a))
                    else:
                        possible_courts = list(set(courts))
                else:
                    courts_t1 = self.tournament["teams"][t1]["courts"]
                    courts_t2 = self.tournament["teams"][t2]["courts"]
                    if len(courts_a) > 0:
                        possible_courts = list(set(courts_a) - (set(courts_t1) | set(courts_t2)))
                    else:
                        possible_courts = list(set(courts) - (set(courts_t1) | set(courts_t2)))

                random.shuffle(possible_courts)
                # print "%s %s %s" % (t1, t2, possible_courts)

                c = possible_courts.pop()
                # print "remove court", c, "in", courts 
                courts.remove(c)

                if self.is_court_a(c):
                    # print "Remove", c, "IN", courts_a
                    courts_a.remove(c)

                games.append((t1, t2, c))

        return games

    def update_teams(self, games):
        for g in games:
            self.tournament["teams"][g[0]]["courts"].append(g[2])
            self.tournament["teams"][g[0]]["games"].append(g[1])

            self.tournament["teams"][g[1]]["courts"].append(g[2])
            self.tournament["teams"][g[1]]["games"].append(g[0])

            if self.is_court_b(g[2]):
                t0_b = self.tournament["teams"][g[0]]["played_b"]
                t1_b = self.tournament["teams"][g[1]]["played_b"]
                self.tournament["teams"][g[0]]["played_b"] = t0_b +1
                self.tournament["teams"][g[1]]["played_b"] = t1_b +1


    def schedule_game(self, tid, possible_teams, team_scheduled):
        if len(possible_teams) > 0:
            oid = random.sample(possible_teams, 1)[0]
            team_scheduled.add(tid)
            team_scheduled.add(oid)
            return tid, oid

        return None, None


    ##################################
    #######    CLI    ################
    ##################################
    def do_use(self, line):
        """use [file_name]
        Opens a tournament file.
        If the fiel does not exist, it will create one.
        """

        file_path='./%s.p' % line

        if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
            f = open(file_path, "rb" )
            self.tournament = pickle.load(f)
            if not self.tournament.get("court_map"):
                self.tournament["court_map"] = dict(a=(1,10), b=(0,0))
            self.set_prompt()
        else:
            self.tournament["name"] = line
            self.save()
            self.set_prompt()

    def do_save(self, line):
        """save
        """
        if self.tournament_loaded():
            self.save()

    # Z for schedule
    def do_zclean(self, line):
        if self.tournament_loaded():

            for _, t in self.tournament["teams"].iteritems():
                t["games"] = []
                t["courts"] = []
                t["played_b"] = 0

            self.save()

    def do_zshow(self, line):
        if self.tournament_loaded():
            try:
                if line == "" or line == "all":
                    rnds = len(self.tournament["teams"].itervalues().next()["games"])
                    for i in range(rnds):
                        self.show_rnd(i)
                else:
                    line = int(line) if line.isdigit() else 1
                    rnd = line -1
                    self.show_rnd(rnd)
            except:
                print("Oops! Something went wrong.")

    def do_zrem(self, line):
        """Removes the last round of games by default. Or the round that is passed as parameter.
Example, > zrem 1
        """
        if self.tournament_loaded():

            if line == "" or line == "all":
                self.remove_rnd(-1)
            else:
                line = int(line) if line.isdigit() else 1
                rnd = line -1
                self.remove_rnd(rnd)

            self.save()


    def do_zexport(self, line):
        if self.tournament_loaded():

            if line == "" or line == "all":
                rnds = len(self.tournament["teams"].itervalues().next()["games"])
                for i in range(rnds):
                    self.export_rnd(i)
            else:
                line = int(line) if line.isdigit() else 1
                rnd = line -1
                self.export_rnd(rnd)


    def do_zmake(self, line, count=0):
        """Schedules one round of a tournament. zmake -f will create the round ignoring previous court assignments
        """
        if self.tournament_loaded():
            games = []
            try:
                games = self.create_round(line)
            except Exception as e:
                print(e)
                print("[DEBUG]", games)
                print("[ERROR] Oops! Something went wrong.")

            if "-v" in line:
                print("[DEBUG] Games", games)

            if games:
                self.update_teams(games)
                self.do_zshow("0")
            else:
                if count < 2:
                    self.do_zmake(line, count+1)
                else:
                    print("Could not create round. Try zmake -f")

            self.save()

    # C for courts
    def do_cset(self, line):
        """List the courts being used and not used per round"""
        if self.tournament_loaded():

            args = line.split(" ")
            if len(args) != 3 or args[0] not in ["a","b"]:
                print("[ERROR] requires 3 paramters. [a|b] [from] [to]")
            self.tournament["court_map"][args[0]] = (int(args[1]), int(args[2]))
            self.save()

    def do_cusage(self, line):
        """Updates the court numbers for section a or b"""
        if self.tournament_loaded():

            if line.isdigit():
                courts, _  = self.court_map()
                rnd = int(line) -1

                used = [v["courts"][rnd] for _, v in self.tournament["teams"].iteritems() if len(v["courts"]) > rnd]
                unused = set(courts) - set(used)

                used2 = sorted(set(used))
                print("Round", line, "used courts")
                print(tabulate([used2], tablefmt="plain"))

                print("Round", line, "unused courts")
                print(tabulate([unused], tablefmt="plain"))

            else:
                print("[ERROR] round number must be a digit.")

    # T for teams
    def do_texport(self, line):
        if self.tournament_loaded():

            data = [[k, v.get("group", "-"), v.get("name", "Anonymous"), v.get("games"), v.get("courts"), v.get("played_b", False)] for k,v in self.tournament["teams"].iteritems()]
            filename = "%s_teams_%d.csv" % (self.tournament["name"], time.time())
            self.export_csv(filename, data)

    def do_trem(self, line):
        if self.tournament_loaded():

            if line.isdigit():
                tid = int(line)
                team = self.tournament.get("teams").get(tid)
                if team:
                    del self.tournament.get("teams")[tid]
                    print("Removed", line, team["name"])
                    self.save()
                else:
                    print("[ERROR] Team", line, "not found.")


    def do_tadd(self, line):
        """tadd [number] [group] [name]
        Same as team.
        Inserts or updates a team into the tournament. Name can contain spaces.
        Should not be used to update after the tournament starts.
        """
        self.do_team(line)

    def do_tlist(self, line):
        if self.tournament_loaded():
            table = [[k, v.get("group", "-"), v.get("name", "Anonymous"), v.get("games"), v.get("courts"), v.get("played_b", 0)] for k,v in self.tournament["teams"].iteritems()]
            if table:
                table.sort()
                print(tabulate(table, tablefmt="grid"))
            print("%d teams" % (len(table)))

    def do_tshow(self, line):
        """Show info for the team"""
        if self.tournament_loaded():

            if line.isdigit():
                tid = int(line)
                team = self.tournament.get("teams").get(tid)
                if team:

                    table = [
                        ["No", line],
                        ["Name", team["name"]],
                        ["Group", team["group"]],
                        ["Played B", team["played_b"]],

                        ]
                    print("Team Info")
                    print(tabulate(table, tablefmt="grid"))

                    table2 = []
                    for rnd in range(len(team["games"])):
                        row = self.format_team_game(tid,team,rnd)
                        table2.append([rnd+1]+row[3:])

                    print("Schedule")
                    print(tabulate(table2, tablefmt="grid"))
                else:
                    print("[ERROR] Team %s not found." % (line))
            else:
                print("[ERROR] Use a team number")

    # G is for games
    def do_gadd(self, line):
        """Adds game to a team. gadd {team_num} {opp_num} {court_num} [-s]
-s options only adds game data to team_num, not opp_num
"""
        if self.tournament_loaded():

            args = line.split(" ")
            if len(args) < 3:
                print("[ERROR] Requries 3 parameters: team_num, opp_num, court_num")
                return

            tid = args[0]
            oid = args[1]
            cid = args[2]

            opts = args[3:] if len(args) > 4 else []

            if not (tid.isdigit() and oid.isdigit() and cid.isdigit()):
                print("[ERROR] team_num, opp_num, court must be digits.")
                return

            tid = int(args[0])
            oid = int(args[1])
            cid = int(args[2])

            team = self.tournament.get("teams").get(tid)
            opp = self.tournament.get("teams").get(oid)

            if team and opp:
                team["games"].append(oid)
                team["courts"].append(cid)

                if "-s" not in opts:
                    opp["games"].append(tid)
                    opp["courts"].append(cid)

                print(tid, team["name"], "vs", oid, opp["name"], "court", cid)
                self.save()
            else:
                print("[ERROR] One or more the teams do not exists.")

    def do_tannex(self, line):
        """tannex [number] [annex]
        Updates team with number of times played annex.
        To be used to """
        if self.tournament_loaded():
            num_annex = line.split(" ")
            if len(num_annex) != 2:
                print("[ERROR] must use tannex [number] [annex] where number and annex are ints")

            num = num_annex[0]
            if num.isdigit():
                num = int(num)
            else:
                print("[ERROR] team number must be int")
                return
            
            annex = num_annex[1]
            if annex.isdigit():
                annex = int(annex)
            else:
                print("[ERROR] team annex must be int")
                return

            if self.tournament.get("teams").get(num):
                # just update the name and group
                self.tournament.get("teams")[num]["played_b"] = annex
                print("Updated", num, "played annex", annex)
            else:
                print("[ERROR] team", num, "does not exists")
                return
                
            self.save()


    def do_team(self, line):
        """team [number] [group] [name]
        Inserts or updates a team into the tournament. Name can contain spaces.
        Should not be used to update after the tournament starts.
        """
        if self.tournament_loaded():
            num_name = line.split(" ")
            if len(num_name) < 3:
                print("[ERROR] must use [number] [group] [name]")

            num = num_name[0]
            if num.isdigit():
                num = int(num)
            else:
                print("[ERROR] team number must be int")
                return

            group = num_name[1]
            name = " ".join(num_name[2:])

            # check if already exists
            if self.tournament.get("teams").get(num):
                # just update the name and group
                old_name = self.tournament.get("teams")[num]["name"]
                old_group = self.tournament.get("teams")[num]["group"]
                self.tournament.get("teams")[num]["name"] = name
                self.tournament.get("teams")[num]["group"] = group
                print("Updated", num, group, name, "from", old_group, old_name)
            else:
                # insert new
                self.tournament.get("teams")[num] = dict(name=name, group=group, games=[], courts=[], played_b=0)
                # print("[INFO] Team added", num, group, name)
            self.save()



    def do_info(self, line):
        """    Prints out a table of pertinent tournament info.
        """
        if self.tournament_loaded():
            table = [
                ["Name", self.tournament.get("name")],
                ["Created", self.tournament.get("created_at")],
                ["Modified",  self.tournament.get("modified_at")],
                ["Courts", self.tournament["court_map"]],
                ["Teams", len(self.tournament["teams"])],
                ]
            print(tabulate(table, tablefmt="grid"))

            if line == "-v":
                pp = pprint.PrettyPrinter(indent=2)
                pp.pprint(self.tournament)


    def do_ls(self, line):
        """Usage:
    ls [teams|schedule]
    Same as list
        """
        if self.tournament_loaded():
            self.do_list(line)

    def do_list(self, line):
        """Usage:
    list [teams | schedule]
    Same as ls
        """
        if self.tournament_loaded():
            if line == "teams":
                self.do_tlist(line)
            elif line == "schedule":
                self.do_zshow(line)


    def do_load(self, line):
        self.read_csv(line)


    #
    def do_EOF(self, line):
        return True


    def do_quit(self,line):
        return True

if __name__ == '__main__':
    cli = PetanqueTournament()
    cli.prompt = '>> '
    cli.intro = """Petanque America Open v0.2.1
Type `help` for more info, `quit` to quit."""

    if len(sys.argv) > 1:
        name = sys.argv[1]
        if name.endswith(".p"):
            name = name[:-2]
        cli.do_use(name)
    else:
        cli.do_use("tournament")

    cli.cmdloop()
