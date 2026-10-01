const entries = [
  {title:"Start fast",category:"Triage",tags:"first blood firstblood quick start split team challenge strategy",text:"Read scope. Find target, port, files, flag format. Get one connection. Split behavior, artifact, and patch work. Share evidence. Submit confirmed flags fast.",cmd:"Check scope → connect once → run focused checks → share result → submit."},
  {title:"Web service",category:"Web",tags:"website web http endpoint directory fuzz api source headers",text:"Read response headers, page source, robots.txt, cookies, and JavaScript. Try the described feature first. Use whatweb and ffuf for focused discovery.",cmd:"curl -i http://TARGET:PORT/\nwhatweb http://TARGET:PORT/"},
  {title:"Binary service",category:"Pwn",tags:"pwn exploit binary socket nc netcat port crash gdb shell",text:"Connect to the service. Inspect the binary. Find input, output, and crash behavior. Use gdb, pwntools, and supplied libc. A reverse connection needs a reachable callback listener.",cmd:"nc -nv TARGET PORT\nfile ./challenge\nchecksec --file=./challenge"},
  {title:"Packet capture",category:"Forensics",tags:"pcap packet wireshark tshark tcp dns http network traffic",text:"Check capture summary and TCP conversations. Filter DNS and HTTP. Follow useful streams. Note packet and stream numbers before extracting data.",cmd:"capinfos capture.pcap\ntshark -r capture.pcap -q -z conv,tcp"},
  {title:"Crypto puzzle",category:"Crypto",tags:"cipher encryption decode xor rsa key nonce hash math",text:"Check encoding, length, repeated blocks, nonce reuse, known plaintext, and hints. Use Sage or Python for a small test. Avoid random cipher guessing.",cmd:"file challenge.txt\nxxd -l 128 challenge.txt"},
  {title:"Image and file clues",category:"Forensics",tags:"stego steganography image hidden data qr barcode metadata png jpg jpeg file",text:"Work on a copy. Check file type, metadata, strings, appended data, and archives. Try QR, steghide, pngcheck. A tool result is a lead, not proof.",cmd:"exiftool artifact\nbinwalk artifact\nzbarimg image.png"},
  {title:"Reverse engineering",category:"Rev",tags:"reverse reversing ghidra disassemble strings elf static analysis",text:"Run ordinary and boundary inputs. Find the success check and trace backward. Use Ghidra for structure, then confirm with a debugger.",cmd:"file program\nstrings -a program | less\nreadelf -h -s program"},
  {title:"Callback setup",category:"Network",tags:"reverse shell callback listen listener connect back nc netcat nat slirp routed tap",text:"NAT gives outbound guest access but no arbitrary inbound callback. Routed mode needs host TAP and callback setup. Test the path with harmless text. Confirm event approval and scope.",cmd:"nc -lvnp PORT\nrednix net callback PORT\n# test with harmless text before challenge payloads"},
  {title:"Attack and defense",category:"A/D",tags:"attack defense attack-defense service patch uptime flag rotate",text:"Inventory ports and health checks. Protect uptime. Reproduce one issue. Patch the cause. Test from clean state. Follow rules when testing other teams.",cmd:"baseline → reproduce → patch → clean test → monitor"},
  {title:"Tulip remote traffic",category:"A/D",tags:"tulip pcap remote capture tcpdump rsync attack defense flags replay",text:"Capture on your defended box, rotate files, and pull completed PCAPs into /var/lib/rednix/tulip/pcaps. Search flags and payloads, inspect flows, then review replay snippets. Full steps: /etc/rednix/tulip.md.",cmd:"tulip init\n# edit /var/lib/rednix/tulip/{tulip.env,services.json}\ntulip start\n# open http://127.0.0.1:3000 in the guest"},
  {title:"ExploitFarm workers",category:"A/D",tags:"exploitfarm xfarm attack defense exploit scheduler farm flags submitter teams",text:"Start the local server, configure teams/timing/submitter in the UI, then create and test an exploit project with xfarm. Keep sources under /work. Full steps: /etc/rednix/exploitfarm.md.",cmd:"exploitfarm start\n# open http://127.0.0.1:5050 in the guest\nxfarm init\nxfarm start --test AUTHORIZED_TEST_HOST"},
  {title:"Outbound network check",category:"Network",tags:"internet outbound network nat dns route curl connectivity",text:"Check route and DNS. NAT should provide outbound IPv4. SSH readiness only proves the VM is reachable from the host.",cmd:"ip route\ncat /etc/resolv.conf\ncurl -I https://example.com"}
];
const expansions = [
  [/\b(shell|callback|call back|connect back|phone home)\b/g," callback listener reverse connection"],
  [/\b(pic|photo|picture|qr|barcode)\b/g," image stego hidden data"],
  [/\b(network dump|wire|traffic|sniff)\b/g," pcap packet capture"],
  [/\b(first blood|firstblood|fastest|quickly|quick)\b/g," triage start fast"],
  [/\b(binary|executable|elf)\b/g," pwn reverse engineering"],
  [/\b(internet|online|connectivity)\b/g," outbound network check"]
];
const form=document.querySelector("#search-form"),input=document.querySelector("#query"),results=document.querySelector("#results"),title=document.querySelector("#result-title"),count=document.querySelector("#result-count");
function search(raw=""){
  const q=raw.toLowerCase().trim();
  title.textContent=q?`Matches for “${raw.trim()}”`:"Quick playbooks";
  let expanded=q; for(const [re,add] of expansions) expanded=expanded.replace(re,`$& ${add}`);
  const terms=[...new Set(expanded.split(/[^a-z0-9]+/).filter(x=>x.length>1))];
  const ranked=entries.map(e=>{const hay=`${e.title} ${e.category} ${e.tags} ${e.text} ${e.cmd}`.toLowerCase();let score=0;for(const t of terms){if(e.title.toLowerCase().includes(t))score+=5;if(e.tags.includes(t))score+=3;if(e.text.toLowerCase().includes(t))score+=1;if(e.cmd.toLowerCase().includes(t))score+=1}return {e,score}}).filter(x=>!q||x.score>0).sort((a,b)=>b.score-a.score);
  count.textContent=q?`${ranked.length} RESULTS · LOCAL SEARCH`:`${entries.length} PLAYBOOKS`;
  results.replaceChildren();
  if(!ranked.length){const p=document.createElement("p");p.className="empty";p.textContent="No match. Try a topic like web, pcap, image, binary, or callback.";results.append(p);return}
  for(const {e} of ranked){const article=document.createElement("article");article.className="result";const meta=document.createElement("div");meta.className="result-top";const cat=document.createElement("b");cat.textContent=e.category;meta.append(cat,document.createTextNode(" / QUICK CHECK"));const h=document.createElement("h3");h.textContent=e.title;const p=document.createElement("p");p.textContent=e.text;const code=document.createElement("code");code.textContent=e.cmd;article.append(meta,h,p,code);results.append(article)}
}
form.addEventListener("submit",e=>{e.preventDefault();search(input.value)});
document.querySelectorAll("[data-query]").forEach(b=>b.addEventListener("click",()=>{input.value=b.dataset.query;search(input.value);input.focus()}));
input.addEventListener("input",()=>search(input.value));
search();
