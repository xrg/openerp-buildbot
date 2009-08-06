function getLatestBuilds()
{
    url = "latestbuilds";
    request = new XMLHttpRequest();
    request.onreadystatechange = function()
    {
     if(request.readyState==4)
        {
         i = request.responseText.indexOf('latest_builds') + 'latest_builds/>'.length
         j = request.responseText.indexOf('</table>',i)
         s = request.responseText.slice(i,j);
         $('#latest_builds').html("<tbody>"+s+"</tbody>");
        }
    }
    request.send(null);
}

