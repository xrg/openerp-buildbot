function getLatestBuilds()
{
    url = "latestbuilds";
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

