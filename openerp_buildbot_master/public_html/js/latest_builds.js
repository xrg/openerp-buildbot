/*function getLatestBuilds()
{
    url = "getLatestBuilds";
    frame = document.getElementById('frame_lastbuild')
    frame.src=url;
    frame_doc=frame.contentWindow.document;
    latest_builds_table = frame_doc.getElementById('latest_builds');
    curr_builds_table = document.getElementById('latest_builds')
    curr_builds_table.innerHTML = latest_builds_table.innerHTML
}*/
function getLatestBuilds()
{
    url = "getLatestBuilds";
    request = new XMLHttpRequest();
    request.open("GET", url, true);
    request.send(null);
    request.onreadystatechange = function()
    {
     if(request.readyState==4)
        {
         i = request.responseText.indexOf('latest_builds') + 'latest_builds/>'.length
         j = request.responseText.indexOf('</table>',i)
         document.getElementById('latest_builds').innerHTML = request.responseText.substring(i,j)
         }
    }
}
/*function child(node){
    for(i in node.childNodes){
       child(node.childNodes[i]);
    }
    alert(node);
    if(node.id == 'latest_builds')
        return node;
    return false;
}
function getLatestBuilds()
{
    url = "getLatestBuilds";
    request = new XMLHttpRequest();
    request.open("GET", url, true);
    request.send(null);
    request.onreadystatechange = function()
    {
     if(request.readyState==4)
        {
         response_doc = document.createElement('div');
         response_doc.innerHTML = request.responseText;
         latse = child(response_doc);
         alert(latse);
         curr_builds_table = document.getElementById('latest_builds132');
         curr_builds_table.innerHTML = response_doc.innerHTML;
        } 
    }
}
*/
