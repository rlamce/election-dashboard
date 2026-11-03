// Generates app/data/dataset.sample.json conforming to CONTRACT.md v1.0.
// All numbers are fictional sample values; margins/swings are computed here so
// the page never has to compute anything.
import fs from "node:fs";
const out = process.argv[2];
const NOW = "2026-11-04T02:35:00Z";
const r1 = x => Math.round(x * 10) / 10;

const races = {};
function race(id, state, fips, office, district, special, label, cands, close, b24, b22) {
  races[id] = { race_id: id, state, state_fips: fips, office, district, special, label,
    candidates: cands.map(c => ({ id: `${id}:${c[0].split(" ").pop().toLowerCase()}`, name: c[0], party: c[1], incumbent: !!c[2] })),
    poll_close_et: close,
    baseline: { "2024": { office: "PRES", D: b24[0], R: b24[1], margin: r1(b24[1]-b24[0]) },
                "2022": { office: b22[2], D: b22[0], R: b22[1], margin: r1(b22[1]-b22[0]) } } };
}
race("PA-SEN-2026","PA","42","SEN",null,false,"Pennsylvania U.S. Senate",[["Dana Whitaker","D"],["Mark Castellano","R"],["Lena Ortiz","L"]],"20:00",[48.7,50.4],[51.2,46.3,"SEN"]);
race("PA-GOV-2026","PA","42","GOV",null,false,"Pennsylvania Governor",[["Josh Reinhart","D",true],["Carla Brennan","R"]],"20:00",[48.7,50.4],[56.5,41.7,"GOV"]);
race("PA-HOU-2026-07","PA","42","HOU","07",false,"Pennsylvania 7th District",[["Susan Wilde","D"],["Ryan Mackenzie","R",true]],"20:00",[47.6,51.3],[51.0,49.0,"HOU"]);
race("OH-SEN-2026-S","OH","39","SEN",null,true,"Ohio U.S. Senate (special)",[["Amy Dolan","D"],["Jon Husted","R",true]],"19:30",[43.9,55.1],[46.5,53.0,"SEN"]);
race("OH-GOV-2026","OH","39","GOV",null,false,"Ohio Governor",[["Tim Keller","D"],["Vivek Ramaswamy","R"]],"19:30",[43.9,55.1],[37.4,62.4,"GOV"]);
race("MI-SEN-2026","MI","26","SEN",null,false,"Michigan U.S. Senate",[["Haley Stevens","D"],["Mike Rogers","R"]],"21:00",[48.3,49.7],[0,0,"SEN"]);
race("MI-GOV-2026","MI","26","GOV",null,false,"Michigan Governor",[["Jocelyn Benson","D"],["John James","R"]],"21:00",[48.3,49.7],[54.5,43.9,"GOV"]);
race("GA-SEN-2026","GA","13","SEN",null,false,"Georgia U.S. Senate",[["Jon Ossoff","D",true],["Buddy Carter","R"]],"19:00",[48.5,50.7],[49.4,48.5,"SEN"]);
race("GA-GOV-2026","GA","13","GOV",null,false,"Georgia Governor",[["Keisha Lance Bottoms","D"],["Burt Jones","R"]],"19:00",[48.5,50.7],[45.9,53.4,"GOV"]);
race("AZ-GOV-2026","AZ","04","GOV",null,false,"Arizona Governor",[["Katie Hobbs","D",true],["Andy Biggs","R"]],"21:00",[46.7,52.2],[50.3,49.6,"GOV"]);
race("NC-SEN-2026","NC","37","SEN",null,false,"North Carolina U.S. Senate",[["Roy Cooper","D"],["Michael Whatley","R"]],"19:30",[47.7,50.9],[0,0,"SEN"]);
race("ME-SEN-2026","ME","23","SEN",null,false,"Maine U.S. Senate",[["Graham Platner","D"],["Susan Collins","R",true]],"20:00",[52.4,45.5],[0,0,"SEN"]);
race("TX-SEN-2026","TX","48","SEN",null,false,"Texas U.S. Senate",[["Colin Allred","D"],["Ken Paxton","R"]],"20:00",[42.5,56.2],[43.5,54.8,"GOV"]);
race("TX-GOV-2026","TX","48","GOV",null,false,"Texas Governor",[["Gina Hinojosa","D"],["Greg Abbott","R",true]],"20:00",[42.5,56.2],[43.8,54.8,"GOV"]);

const J = {};
function jur(jkey, level, name, state, state_fips, parent, b24, b22) {
  J[jkey] = { jkey, level, name, state, state_fips, parent,
    baseline: { "2024": { PRES: { D: b24[0], R: b24[1], margin: r1(b24[1]-b24[0]), total_votes: b24[2] || 0 } },
                "2022": b22 || {} },
    results: {} };
  return J[jkey];
}
const src = (id, tier, url) => ({ id, tier, url, ts: NOW });
function result(jkey, raceId, o) {
  const j = J[jkey]; const b24 = j.baseline["2024"].PRES.margin;
  const b22 = (j.baseline["2022"][races[raceId].office] || {}).margin;
  const pct = o.pct || { D: null, R: null, O: null };
  const margin = (pct.D != null && pct.R != null) ? r1(pct.R - pct.D) : null;
  const leader = margin == null ? null : (margin > 0 ? "R" : margin < 0 ? "D" : null);
  const votes = {};
  for (const c of races[raceId].candidates) votes[c.id] = (o.votes && o.votes[c.party]) || 0;
  j.results[raceId] = {
    status: o.status, confidence: o.confidence, pct_reporting: o.rep ?? null,
    votes, pct, leader: o.leader !== undefined ? o.leader : leader, margin,
    swing_vs_2024: margin == null ? null : r1(margin - b24),
    swing_vs_2022: (margin == null || b22 == null || b22 === 0) ? null : r1(margin - b22),
    called: !!o.called, called_by: o.called ? (o.called_by || "AP") : null, called_at: o.called ? "2026-11-04T02:12:00Z" : null,
    range: o.range || null, inherited_from: o.inherited_from || null,
    sources_used: o.used || [], sources_rejected: o.rejected || [], updated_at: o.updated || NOW
  };
}

// ---- National + states
jur("US","national","United States",null,null,null,[48.3,49.8,155000000]);
jur("42","state","Pennsylvania","PA","42","US",[48.7,50.4,7000000],{SEN:{D:51.2,R:46.3,margin:-4.9},GOV:{D:56.5,R:41.7,margin:-14.8}});
jur("39","state","Ohio","OH","39","US",[43.9,55.1,5900000],{SEN:{D:46.5,R:53.0,margin:6.5},GOV:{D:37.4,R:62.4,margin:25.0}});
jur("26","state","Michigan","MI","26","US",[48.3,49.7,5600000],{GOV:{D:54.5,R:43.9,margin:-10.6}});
jur("13","state","Georgia","GA","13","US",[48.5,50.7,5200000],{SEN:{D:49.4,R:48.5,margin:-0.9},GOV:{D:45.9,R:53.4,margin:7.5}});
jur("04","state","Arizona","AZ","04","US",[46.7,52.2,3400000],{GOV:{D:50.3,R:49.6,margin:-0.7}});
jur("37","state","North Carolina","NC","37","US",[47.7,50.9,5700000],{});
jur("23","state","Maine","ME","23","US",[52.4,45.5,840000],{});
jur("48","state","Texas","TX","48","US",[42.5,56.2,11400000],{GOV:{D:43.8,R:54.8,margin:11.0}});

const PA_DOS = src("src-pa-dos","official","https://www.electionreturns.pa.gov/");
const AP = src("src-ap","media_t1","https://apnews.com/hub/election-results");
result("42","PA-SEN-2026",{status:"official_preliminary",confidence:72,rep:63.4,pct:{D:49.8,R:47.9,O:2.3},votes:{D:2201455,R:2117490,L:101688},used:[PA_DOS,AP],rejected:[{id:"src-x-1",reason:"unsourced social post claiming 100% reporting"}]});
result("42","PA-GOV-2026",{status:"official_preliminary",confidence:81,rep:63.4,pct:{D:55.1,R:43.6,O:1.3},votes:{D:2435100,R:1926800},called:true,called_by:"AP",used:[PA_DOS,AP]});
result("42","PA-HOU-2026-07",{status:"estimated",confidence:44,rep:38.0,pct:{D:50.6,R:49.4,O:0},votes:{D:98120,R:95790},used:[AP],rejected:[{id:"src-x-2",reason:"tier-3 account, figures contradict official feed"}]});
const OH_SOS = src("src-oh-sos","official","https://www.ohiosos.gov/elections/election-results-and-data/");
result("39","OH-SEN-2026-S",{status:"official_preliminary",confidence:88,rep:91.2,pct:{D:44.1,R:54.6,O:1.3},votes:{D:1902330,R:2355210},called:true,called_by:"AP",used:[OH_SOS,AP]});
result("39","OH-GOV-2026",{status:"official_preliminary",confidence:90,rep:91.2,pct:{D:41.8,R:57.0,O:1.2},votes:{D:1803000,R:2458600},called:true,called_by:"AP",used:[OH_SOS,AP]});
result("26","MI-SEN-2026",{status:"contested",confidence:35,rep:58.7,pct:{D:49.1,R:48.8,O:2.1},votes:{D:1611230,R:1601380},range:{D:[47.9,50.4],R:[47.6,50.1]},used:[AP,src("src-detroit-fp","media_t2","https://www.freep.com/elections")],rejected:[{id:"src-x-3",reason:"two tier-1 outlets disagree by more than 2 points"}]});
result("26","MI-GOV-2026",{status:"estimated",confidence:52,rep:58.7,pct:{D:51.2,R:46.9,O:1.9},votes:{D:1680000,R:1539000},used:[AP]});
const GA_SOS = src("src-ga-sos","official","https://results.enr.clarityelections.com/GA/");
result("13","GA-SEN-2026",{status:"official_preliminary",confidence:66,rep:77.9,pct:{D:50.3,R:48.4,O:1.3},votes:{D:2012400,R:1936300},used:[GA_SOS,AP]});
result("13","GA-GOV-2026",{status:"official_preliminary",confidence:70,rep:77.9,pct:{D:47.4,R:51.6,O:1.0},votes:{D:1896000,R:2064000},used:[GA_SOS,AP]});
result("04","AZ-GOV-2026",{status:"estimated",confidence:28,rep:21.5,pct:{D:51.9,R:46.8,O:1.3},votes:{D:402300,R:362800},used:[AP]});
result("37","NC-SEN-2026",{status:"pending",confidence:0,rep:null,used:[],rejected:[{id:"src-x-4",reason:"exit-poll screenshot, no outlet attribution"}]});
result("23","ME-SEN-2026",{status:"official_preliminary",confidence:58,rep:47.0,pct:{D:50.9,R:47.7,O:1.4},votes:{D:206400,R:193400},used:[src("src-me-sos","official","https://www.maine.gov/sos/cec/elec/results/"),AP]});
result("48","TX-SEN-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:45.2,R:53.4,O:1.4},votes:{D:4950000,R:5848000},called:true,called_by:"AP",used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP]});
result("48","TX-GOV-2026",{status:"official_certified",confidence:98,rep:100,pct:{D:43.1,R:55.6,O:1.3},votes:{D:4720000,R:6089000},called:true,called_by:"AP",used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP]});

// ---- PA counties
const PA = [
  ["42101","Philadelphia",[78.9,20.1],{D:80.4,R:18.3,O:1.3},92.1,"official_preliminary",88,true],
  ["42003","Allegheny",[60.2,38.6],{D:61.0,R:37.5,O:1.5},71.3,"official_preliminary",74,false],
  ["42017","Bucks",[48.9,50.0],{D:50.2,R:48.6,O:1.2},55.0,"official_preliminary",61,false],
  ["42091","Montgomery",[60.9,38.0],{D:62.3,R:36.4,O:1.3},66.8,"official_preliminary",77,false],
  ["42045","Delaware",[62.9,36.1],{D:63.8,R:35.0,O:1.2},60.1,"official_preliminary",70,false],
  ["42029","Chester",[56.2,42.6],{D:57.0,R:41.7,O:1.3},48.9,"official_preliminary",59,false],
  ["42071","Lancaster",[40.2,58.3],{D:41.1,R:57.6,O:1.3},80.4,"official_preliminary",83,false],
  ["42077","Lehigh",[52.3,46.5],{D:52.0,R:46.7,O:1.3},44.2,"estimated",41,false],
  ["42095","Northampton",[49.0,49.9],{D:48.1,R:50.5,O:1.4},39.7,"estimated",38,false],
  ["42049","Erie",[48.8,49.9],{D:49.2,R:49.5,O:1.3},62.0,"contested",31,false],
  ["42011","Berks",[43.8,54.9],{D:44.0,R:54.7,O:1.3},70.2,"official_preliminary",72,false],
  ["42069","Lackawanna",[51.9,47.0],{D:51.3,R:47.4,O:1.3},58.8,"official_preliminary",64,false],
  ["42079","Luzerne",[38.7,60.2],{D:39.4,R:59.3,O:1.3},74.5,"official_preliminary",78,false],
  ["42133","York",[35.2,63.5],{D:35.9,R:62.8,O:1.3},83.1,"official_preliminary",85,false],
  ["42043","Dauphin",[54.2,44.5],{D:55.0,R:43.7,O:1.3},61.5,"official_preliminary",68,false],
  ["42027","Centre",[52.8,45.6],{D:53.4,R:45.2,O:1.4},12.0,"estimated",19,false],
  ["42129","Westmoreland",[34.5,64.4],null,null,"pending",0,false],
  ["42125","Washington",[36.9,62.0],null,null,"pending",0,false],
  ["42019","Butler",[31.5,67.3],{D:32.0,R:66.7,O:1.3},88.0,"official_preliminary",86,false],
  ["42021","Cambria",[29.6,69.5],null,null,"pending",0,false],
];
for (const [fips,name,b24,pct,rep,status,conf,called] of PA) {
  jur(fips,"county",name,"PA","42","42",b24,{SEN:{D:r1(b24[0]+2.5),R:r1(b24[1]-3.5),margin:r1((b24[1]-3.5)-(b24[0]+2.5))},GOV:{D:r1(b24[0]+7),R:r1(b24[1]-8),margin:r1((b24[1]-8)-(b24[0]+7))}});
  const base = {status,confidence:conf,rep,pct:pct||undefined,used: status==="pending"?[]:[PA_DOS, ...(status==="estimated"||status==="contested"?[AP]:[])]};
  if (status==="contested") { base.range = {D:[47.5,51.0],R:[47.8,51.2]}; base.rejected=[{id:"src-x-erie",reason:"county site and AP feed disagree on precincts reporting"}]; }
  result(fips,"PA-SEN-2026",{...base, votes: pct?{D:Math.round(pct.D*4000*rep/100),R:Math.round(pct.R*4000*rep/100)}:undefined, called});
  const gpct = pct ? {D:r1(pct.D+4.5),R:r1(pct.R-5.5),O:1.0} : undefined;
  result(fips,"PA-GOV-2026",{status,confidence:conf,rep,pct:gpct,votes:gpct?{D:Math.round(gpct.D*4000*rep/100),R:Math.round(gpct.R*4000*rep/100)}:undefined,used:base.used,called: status!=="pending" && conf>60});
}
// PA-07 is Lehigh + Northampton + part of Monroe
result("42077","PA-HOU-2026-07",{status:"estimated",confidence:40,rep:44.2,pct:{D:51.0,R:49.0,O:0},votes:{D:52100,R:50060},used:[AP]});
result("42095","PA-HOU-2026-07",{status:"estimated",confidence:36,rep:39.7,pct:{D:49.6,R:50.4,O:0},votes:{D:41200,R:41860},used:[AP]});

// ---- PA cities
jur("42101:philadelphia","city","Philadelphia","PA","42","42101",[78.9,20.1]);
result("42101:philadelphia","PA-SEN-2026",{status:"official_preliminary",confidence:85,rep:92.1,pct:{D:80.4,R:18.3,O:1.3},votes:{D:532100,R:121050},used:[src("src-phila-cc","official","https://vote.phila.gov/results/")],called:true});
result("42101:philadelphia","PA-GOV-2026",{status:"official_preliminary",confidence:86,rep:92.1,pct:{D:84.1,R:14.6,O:1.3},votes:{D:556500,R:96600},used:[src("src-phila-cc","official","https://vote.phila.gov/results/")],called:true});
jur("42003:pittsburgh","city","Pittsburgh","PA","42","42003",[60.2,38.6]);
result("42003:pittsburgh","PA-SEN-2026",{status:"official_preliminary",confidence:74,rep:71.3,pct:{D:61.0,R:37.5,O:1.5},votes:{D:0,R:0},inherited_from:"42003",used:[PA_DOS]});
result("42003:pittsburgh","PA-GOV-2026",{status:"official_preliminary",confidence:74,rep:71.3,pct:{D:65.5,R:32.0,O:1.0},votes:{D:0,R:0},inherited_from:"42003",used:[PA_DOS]});
jur("42077:allentown","city","Allentown","PA","42","42077",[52.3,46.5]);
result("42077:allentown","PA-SEN-2026",{status:"estimated",confidence:41,rep:44.2,pct:{D:52.0,R:46.7,O:1.3},votes:{D:0,R:0},inherited_from:"42077",used:[PA_DOS,AP]});

// ---- OH counties
const OH = [["39035","Cuyahoga",[65.1,33.8],{D:64.2,R:34.6,O:1.2},95.0,"official_preliminary",90,true],["39049","Franklin",[63.8,34.9],{D:63.0,R:35.8,O:1.2},93.4,"official_preliminary",89,true],["39061","Hamilton",[57.0,41.6],{D:56.1,R:42.7,O:1.2},90.0,"official_preliminary",86,true],["39153","Summit",[54.1,44.6],{D:53.0,R:45.8,O:1.2},88.2,"official_preliminary",84,true]];
for (const [fips,name,b24,pct,rep,status,conf,called] of OH) {
  jur(fips,"county",name,"OH","39","39",b24,{SEN:{D:r1(b24[0]+1),R:r1(b24[1]-2),margin:r1((b24[1]-2)-(b24[0]+1))}});
  result(fips,"OH-SEN-2026-S",{status,confidence:conf,rep,pct,votes:{D:Math.round(pct.D*5000),R:Math.round(pct.R*5000)},used:[OH_SOS,AP],called});
  result(fips,"OH-GOV-2026",{status,confidence:conf,rep,pct:{D:r1(pct.D-2),R:r1(pct.R+2),O:pct.O},votes:{D:Math.round((pct.D-2)*5000),R:Math.round((pct.R+2)*5000)},used:[OH_SOS,AP],called});
}
// ---- MI counties (contested state)
jur("26163","county","Wayne","MI","26","26",[63.1,35.2],{GOV:{D:67.0,R:31.5,margin:-35.5}});
result("26163","MI-SEN-2026",{status:"contested",confidence:30,rep:41.0,pct:{D:64.0,R:34.1,O:1.9},votes:{D:280100,R:149300},range:{D:[62.5,66.0],R:[32.0,35.5]},used:[AP],rejected:[{id:"src-x-wayne",reason:"county clerk feed stalled since 01:10 UTC; media figures unconfirmed"}]});
result("26163","MI-GOV-2026",{status:"estimated",confidence:45,rep:41.0,pct:{D:66.2,R:32.0,O:1.8},votes:{D:289700,R:140000},used:[AP]});
jur("26125","county","Oakland","MI","26","26",[55.4,43.1],{GOV:{D:60.0,R:38.5,margin:-21.5}});
result("26125","MI-SEN-2026",{status:"estimated",confidence:50,rep:66.0,pct:{D:55.9,R:42.3,O:1.8},votes:{D:310200,R:234700},used:[AP]});
result("26125","MI-GOV-2026",{status:"estimated",confidence:52,rep:66.0,pct:{D:58.0,R:40.3,O:1.7},votes:{D:321900,R:223600},used:[AP]});
jur("26099","county","Macomb","MI","26","26",[41.1,57.5],{GOV:{D:46.0,R:52.5,margin:6.5}});
result("26099","MI-SEN-2026",{status:"estimated",confidence:48,rep:62.0,pct:{D:42.6,R:55.4,O:2.0},votes:{D:150300,R:195400},used:[AP]});
// ---- GA counties
jur("13121","county","Fulton","GA","13","13",[72.6,26.3],{SEN:{D:72.0,R:26.9,margin:-45.1}});
result("13121","GA-SEN-2026",{status:"official_preliminary",confidence:70,rep:81.0,pct:{D:73.5,R:25.4,O:1.1},votes:{D:380200,R:131400},used:[GA_SOS,AP]});
result("13121","GA-GOV-2026",{status:"official_preliminary",confidence:72,rep:81.0,pct:{D:70.1,R:29.0,O:0.9},votes:{D:362600,R:150000},used:[GA_SOS,AP]});
jur("13089","county","DeKalb","GA","13","13",[81.3,17.7],{SEN:{D:82.0,R:17.1,margin:-64.9}});
result("13089","GA-SEN-2026",{status:"official_preliminary",confidence:73,rep:85.2,pct:{D:82.6,R:16.5,O:0.9},votes:{D:260800,R:52100},used:[GA_SOS,AP]});
jur("13067","county","Cobb",  "GA","13","13",[55.6,43.1],{SEN:{D:55.0,R:43.8,margin:-11.2}});
result("13067","GA-SEN-2026",{status:"official_preliminary",confidence:64,rep:70.5,pct:{D:56.2,R:42.6,O:1.2},votes:{D:200100,R:151700},used:[GA_SOS,AP]});
// ---- AZ counties
jur("04013","county","Maricopa","AZ","04","04",[47.3,51.7],{GOV:{D:50.8,R:49.1,margin:-1.7}});
result("04013","AZ-GOV-2026",{status:"estimated",confidence:25,rep:18.2,pct:{D:52.4,R:46.3,O:1.3},votes:{D:260300,R:230000},used:[AP]});
jur("04019","county","Pima","AZ","04","04",[57.9,40.3],{GOV:{D:59.0,R:40.0,margin:-19.0}});
result("04019","AZ-GOV-2026",{status:"estimated",confidence:30,rep:30.0,pct:{D:60.2,R:38.5,O:1.3},votes:{D:95500,R:61100},used:[AP]});
// ---- NC counties pending
jur("37119","county","Mecklenburg","NC","37","37",[66.1,32.3]);
result("37119","NC-SEN-2026",{status:"pending",confidence:0,rep:null,used:[]});
jur("37183","county","Wake","NC","37","37",[61.7,36.4]);
result("37183","NC-SEN-2026",{status:"pending",confidence:0,rep:null,used:[]});
// ---- TX counties
jur("48201","county","Harris","TX","48","48",[52.0,46.9],{GOV:{D:50.0,R:48.9,margin:-1.1}});
result("48201","TX-SEN-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:54.5,R:44.3,O:1.2},votes:{D:830200,R:674800},used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP],called:true});
result("48201","TX-GOV-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:51.9,R:46.9,O:1.2},votes:{D:790600,R:714400},used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP],called:true});
jur("48113","county","Dallas","TX","48","48",[61.3,37.5],{GOV:{D:60.0,R:38.9,margin:-21.1}});
result("48113","TX-SEN-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:63.0,R:35.8,O:1.2},votes:{D:520100,R:295500},used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP],called:true});
jur("48453","county","Travis","TX","48","48",[70.9,26.6],{GOV:{D:69.0,R:29.5,margin:-39.5}});
result("48453","TX-SEN-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:71.9,R:26.5,O:1.6},votes:{D:380300,R:140100},used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP],called:true});
jur("48029","county","Bexar","TX","48","48",[55.6,43.0]);
result("48029","TX-SEN-2026",{status:"official_certified",confidence:97,rep:100,pct:{D:57.3,R:41.4,O:1.3},votes:{D:330200,R:238600},used:[src("src-tx-sos","official","https://results.texas-election.com/"),AP],called:true});

const videos = [
  { id:"vid-pbs", platform:"youtube", kind:"channel_live", youtube_channel_id:"UC6ZFN9Tx6xh-skXCuRHCDpQ", youtube_video_id:null, title:"PBS NewsHour election night live", channel:"PBS NewsHour", tier:"major_outlet", live:true, started_at:"2026-11-03T23:00:00Z", scope:{level:"national",jkey:"US"}, location_confidence:"exact", embed_url:"https://www.youtube.com/embed/live_stream?channel=UC6ZFN9Tx6xh-skXCuRHCDpQ&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UC6ZFN9Tx6xh-skXCuRHCDpQ/live", muted:true, rank:1 },
  { id:"vid-ap", platform:"youtube", kind:"channel_live", youtube_channel_id:"UC52X5wxOL_s5yw0dQk7NtgA", youtube_video_id:null, title:"AP live: Midterm election results", channel:"Associated Press", tier:"major_outlet", live:true, started_at:"2026-11-03T22:30:00Z", scope:{level:"national",jkey:"US"}, location_confidence:"exact", embed_url:"https://www.youtube.com/embed/live_stream?channel=UC52X5wxOL_s5yw0dQk7NtgA&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UC52X5wxOL_s5yw0dQk7NtgA/live", muted:true, rank:2 },
  { id:"vid-cspan", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCb--64Gl51jIEVE-GLDAVTg", youtube_video_id:null, title:"C-SPAN: Election night coverage and candidate speeches", channel:"C-SPAN", tier:"official", live:null, started_at:null, scope:{level:"national",jkey:"US"}, location_confidence:"exact", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCb--64Gl51jIEVE-GLDAVTg&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCb--64Gl51jIEVE-GLDAVTg/live", muted:true, rank:3 },
  { id:"vid-nbc", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCeY0bbntWzzVIaj2z3QigXg", youtube_video_id:null, title:"NBC News NOW: Decision 2026", channel:"NBC News", tier:"major_outlet", live:true, started_at:"2026-11-03T23:00:00Z", scope:{level:"national",jkey:"US"}, location_confidence:"exact", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCeY0bbntWzzVIaj2z3QigXg&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCeY0bbntWzzVIaj2z3QigXg/live", muted:true, rank:4 },
  { id:"vid-whyy", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-WHYY00000000", youtube_video_id:null, title:"WHYY: Pennsylvania election night special", channel:"WHYY (PBS Philadelphia)", tier:"regional_outlet", live:true, started_at:"2026-11-04T00:00:00Z", scope:{level:"state",jkey:"42"}, location_confidence:"state", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-WHYY00000000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-WHYY00000000/live", muted:true, rank:1 },
  { id:"vid-6abc", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-6ABC00000000", youtube_video_id:null, title:"6abc Action News: Philadelphia results desk", channel:"6abc Philadelphia", tier:"regional_outlet", live:true, started_at:"2026-11-04T00:30:00Z", scope:{level:"city",jkey:"42101:philadelphia"}, location_confidence:"city", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-6ABC00000000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-6ABC00000000/live", muted:true, rank:1 },
  { id:"vid-kdka", platform:"youtube", kind:"video", youtube_channel_id:"UCSAMPLE-KDKA00000000", youtube_video_id:"SAMPLEvid01", title:"KDKA: Allegheny County returns, Senate race watch party", channel:"KDKA-TV Pittsburgh", tier:"regional_outlet", live:false, started_at:"2026-11-04T01:10:00Z", scope:{level:"county",jkey:"42003"}, location_confidence:"exact", embed_url:"https://www.youtube.com/embed/SAMPLEvid01?mute=1&autoplay=1", link_url:"https://www.youtube.com/watch?v=SAMPLEvid01", muted:true, rank:2 },
  { id:"vid-wcpo", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-WCPO00000000", youtube_video_id:null, title:"WCPO 9: Ohio Senate special election coverage", channel:"WCPO Cincinnati", tier:"regional_outlet", live:true, started_at:"2026-11-04T00:00:00Z", scope:{level:"county",jkey:"39061"}, location_confidence:"city", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-WCPO00000000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-WCPO00000000/live", muted:true, rank:1 },
  { id:"vid-gpb", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-GPB000000000", youtube_video_id:null, title:"GPB: Georgia decides 2026", channel:"Georgia Public Broadcasting", tier:"regional_outlet", live:true, started_at:"2026-11-03T23:30:00Z", scope:{level:"state",jkey:"13"}, location_confidence:"state", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-GPB000000000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-GPB000000000/live", muted:true, rank:1 },
  { id:"vid-mi-stream", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-MISTREAM0000", youtube_video_id:null, title:"Detroit count watch (independent stream)", channel:"MotorCityLive", tier:"unverified", live:true, started_at:"2026-11-04T01:40:00Z", scope:{level:"county",jkey:"26163"}, location_confidence:"inferred", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-MISTREAM0000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-MISTREAM0000/live", muted:true, rank:3 },
  { id:"vid-azfam", platform:"youtube", kind:"channel_live", youtube_channel_id:"UCSAMPLE-AZFAM0000000", youtube_video_id:null, title:"Arizona's Family: Governor's race live", channel:"AZFamily", tier:"regional_outlet", live:true, started_at:"2026-11-04T02:00:00Z", scope:{level:"state",jkey:"04"}, location_confidence:"state", embed_url:"https://www.youtube.com/embed/live_stream?channel=UCSAMPLE-AZFAM0000000&mute=1&autoplay=1", link_url:"https://www.youtube.com/channel/UCSAMPLE-AZFAM0000000/live", muted:true, rank:1 },
];

const changes = [
  { ts:"2026-11-04T00:00:30Z", type:"polls_closed", race_id:null, jkey:"US", official:true, important:false, text:"Polls closed in Pennsylvania, Maine, Texas and 13 other states." },
  { ts:"2026-11-04T01:05:00Z", type:"newly_official", race_id:"PA-SEN-2026", jkey:"42", official:true, important:false, text:"Pennsylvania Senate: first official county returns posted by the Department of State." },
  { ts:"2026-11-04T01:48:00Z", type:"contested", race_id:"MI-SEN-2026", jkey:"26", official:false, important:true, text:"Michigan Senate marked contested: AP and Detroit Free Press figures differ by more than two points." },
  { ts:"2026-11-04T02:12:00Z", type:"race_called", race_id:"OH-SEN-2026-S", jkey:"39", official:true, important:true, text:"Ohio Senate special: officially called for Jon Husted (R) with 91 percent of precincts reporting." },
  { ts:"2026-11-04T02:12:30Z", type:"race_called", race_id:"TX-SEN-2026", jkey:"48", official:true, important:true, text:"Texas Senate: certified for Ken Paxton (R)." },
  { ts:"2026-11-04T02:20:00Z", type:"race_called", race_id:"PA-GOV-2026", jkey:"42", official:true, important:true, text:"Pennsylvania Governor: officially called for Josh Reinhart (D)." },
  { ts:"2026-11-04T02:31:00Z", type:"confidence_shift", race_id:"AZ-GOV-2026", jkey:"04", official:false, important:false, text:"Arizona Governor: confidence down to 28 as early Maricopa ballots shift the margin." },
];

const dataset = {
  meta: { schema_version:"1.0", generated_at: NOW, refresh_id:"r-0007", previous_refresh_id:"r-0006", election_date:"2026-11-03", stale:false,
    note: "SAMPLE DATA. Candidate names, figures and sources are illustrative placeholders for dashboard testing.",
    agents: { official:{ok:true,ran_at:NOW,note:""}, media:{ok:true,ran_at:NOW,note:""}, scoring:{ok:true,ran_at:NOW,note:""}, video:{ok:false,ran_at:"2026-11-04T02:05:00Z",note:"YouTube live-check timed out; carried previous list"} } },
  national: { headline:"Sample data: Ohio and Texas Senate seats called for Republicans; Pennsylvania and Michigan still counting.", overall_confidence:61, states_with_official_data:6,
    chambers: { SEN:{ not_up:{D:28,R:37,I:2}, called:{D:0,R:2,I:0}, undecided:33, majority:51 }, HOU:{ called:{D:112,R:118}, undecided:205, majority:218 }, GOV:{ not_up:{D:9,R:5}, called:{D:1,R:2}, undecided:33 } } },
  races, jurisdictions: J, videos, changes,
  briefing: {
    on_open: "Good evening. As of 9:35 PM Eastern, this is sample data. Ohio's Senate special and Texas Senate have been called for Republicans. Pennsylvania's Senate race is a two-point Democratic lead with 63 percent reporting, and Michigan's Senate race is contested.",
    delta: "Since your last look: Pennsylvania Governor was officially called for the Democrat, and Arizona's governor race confidence fell to 28.",
    alerts: [ "Ohio Senate special officially called for Jon Husted.", "Texas Senate certified for Ken Paxton.", "Pennsylvania Governor officially called for Josh Reinhart." ]
  },
  sources: {
    official: { PA:{ name:"Pennsylvania Department of State", url:"https://www.electionreturns.pa.gov/", feed:{type:"json",url:"https://www.electionreturns.pa.gov/api/"} }, OH:{ name:"Ohio Secretary of State", url:"https://www.ohiosos.gov/elections/election-results-and-data/", feed:{type:"html",url:""} }, GA:{ name:"Georgia Secretary of State", url:"https://results.enr.clarityelections.com/GA/", feed:{type:"json",url:""} }, TX:{ name:"Texas Secretary of State", url:"https://results.texas-election.com/", feed:{type:"json",url:""} } },
    media_tiers: { "1":["AP","Reuters","NBC News","ABC News","CBS News","CNN","Fox News","PBS"], "2":["state and regional newspapers and TV stations"], "3":["official or very-high-reach accounts on two or more platforms"] }
  }
};
fs.writeFileSync(out, JSON.stringify(dataset, null, 1));
console.log("jurisdictions", Object.keys(J).length, "races", Object.keys(races).length, "videos", videos.length, "bytes", fs.statSync(out).size);
