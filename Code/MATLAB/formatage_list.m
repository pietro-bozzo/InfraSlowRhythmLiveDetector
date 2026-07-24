function Liste_new = formatage_list(liste,start_sec_decay)
    % transforme la liste 1xN en Nx2 en ajoutant le start_sec_decay
    n = numel(liste);
    %%%%%%%%%Eviter un élément en trop (i.e. un intervalle sans end)
    % Si nombre impair → on enlève le dernier élément
    if mod(n,2) ~= 0
        warning('Liste impaire détectée → dernier élément ignoré');
        liste = liste(1:end-1);
        n = n - 1;
    end
    %%%%%%%%%
    Liste_new = zeros(ceil(n/2),2);
    for i = 1:n
        row = ceil(i/2);
        col = mod(i-1,2) + 1;
        Liste_new(row, col) = liste(i);
    end
    % The list with all the intervals detected by open-ephys detector :
    Liste_new = Liste_new + start_sec_decay;
end